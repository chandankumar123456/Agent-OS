package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net"
	"sync"
	"time"

	"github.com/AgentOS/supervisor/proto"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"
)

// CheckpointServer implements the CheckpointServiceServer interface
type CheckpointServer struct {
	proto.UnimplementedCheckpointServiceServer
	mu            sync.RWMutex
	checkpoints   map[string]*proto.Checkpoint
	checkpointSub map[string]chan *proto.CheckpointEvent
	db            *DB
	logger        *log.Logger
	grpcServer    *grpc.Server
	port          int
}

// NewCheckpointServer creates a new checkpoint server
func NewCheckpointServer(db *DB, logger *log.Logger) *CheckpointServer {
	return &CheckpointServer{
		checkpoints:   make(map[string]*proto.Checkpoint),
		checkpointSub: make(map[string]chan *proto.CheckpointEvent),
		db:            db,
		logger:        logger,
	}
}

// SaveCheckpoint saves a checkpoint to the database
func (s *CheckpointServer) SaveCheckpoint(ctx context.Context, req *proto.SaveCheckpointRequest) (*proto.SaveCheckpointResponse, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	// Generate unique checkpoint ID
	checkpointID := fmt.Sprintf("checkpoint_%d", time.Now().UnixNano())

	// Create checkpoint
	checkpoint := &proto.Checkpoint{
		Id:             checkpointID,
		ThreadId:       req.ThreadId,
		CheckpointNs:   time.Now().UnixNano(),
		CheckpointType: req.CheckpointType,
		CreatedAt:      timestamppb.Now(),
		UpdatedAt:      timestamppb.Now(),
		StateBlob:      req.StateBlob,
		ChannelValues:  req.ChannelValues,
		PendingSends:   req.PendingSends,
		ParentIds:      req.ParentIds,
		Metadata:       req.Metadata,
		TaskId:         req.TaskId,
	}

	// Store checkpoint
	s.checkpoints[checkpointID] = checkpoint

	// Create event
	event := &proto.CheckpointEvent{
		CheckpointId: checkpointID,
		ThreadId:     req.ThreadId,
		EventType:    proto.CheckpointEventType_CHECKPOINT_EVENT_CREATED,
		Timestamp:    timestamppb.Now(),
		Checkpoint:   checkpoint,
	}

	// Notify subscribers
	if ch, ok := s.checkpointSub[req.ThreadId]; ok {
		select {
		case ch <- event:
		default:
			// Subscriber not ready, skip
		}
	}

	// Save to database
	if err := s.saveCheckpointToDB(checkpoint); err != nil {
		s.logger.Printf("Warning: Failed to save checkpoint to database: %v", err)
	}

	return &proto.SaveCheckpointResponse{
		Success:      true,
		CheckpointId: checkpointID,
	}, nil
}

// GetCheckpoint retrieves a checkpoint by ID
func (s *CheckpointServer) GetCheckpoint(ctx context.Context, req *proto.GetCheckpointRequest) (*proto.GetCheckpointResponse, error) {
	s.mu.RLock()
	checkpoint, ok := s.checkpoints[req.CheckpointId]
	s.mu.RUnlock()

	if !ok {
		// Try to load from database
		checkpoint, err := s.loadCheckpointFromDB(req.CheckpointId)
		if err != nil {
			return nil, status.Error(codes.NotFound, "checkpoint not found")
		}
		return &proto.GetCheckpointResponse{
			Success:  true,
			Checkpoint: checkpoint,
		}, nil
	}

	return &proto.GetCheckpointResponse{
		Success:    true,
		Checkpoint: checkpoint,
	}, nil
}

// ListCheckpoints lists checkpoints for a thread with pagination
func (s *CheckpointServer) ListCheckpoints(ctx context.Context, req *proto.ListCheckpointsRequest) (*proto.ListCheckpointsResponse, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	var checkpoints []*proto.Checkpoint
	for _, cp := range s.checkpoints {
		if cp.ThreadId == req.ThreadId {
			checkpoints = append(checkpoints, cp)
		}
	}

	// Sort by timestamp (newest first)
	for i := 0; i < len(checkpoints)-1; i++ {
		for j := i + 1; j < len(checkpoints); j++ {
			if checkpoints[j].CheckpointNs > checkpoints[i].CheckpointNs {
				checkpoints[i], checkpoints[j] = checkpoints[j], checkpoints[i]
			}
		}
	}

	// Apply pagination
	start := int(req.Offset)
	if start >= len(checkpoints) {
		checkpoints = []*proto.Checkpoint{}
	} else {
		end := start + int(req.Limit)
		if end > len(checkpoints) {
			end = len(checkpoints)
		}
		checkpoints = checkpoints[start:end]
	}

	return &proto.ListCheckpointsResponse{
		Success:     true,
		Checkpoints: checkpoints,
		TotalCount:  int32(len(checkpoints)),
	}, nil
}

// GetLatestCheckpoint gets the most recent checkpoint for a thread
func (s *CheckpointServer) GetLatestCheckpoint(ctx context.Context, req *proto.GetLatestCheckpointRequest) (*proto.GetCheckpointResponse, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	var latestCheckpoint *proto.Checkpoint
	var latestTime int64 = -1

	for _, cp := range s.checkpoints {
		if cp.ThreadId == req.ThreadId && cp.CheckpointNs > latestTime {
			latestTime = cp.CheckpointNs
			latestCheckpoint = cp
		}
	}

	if latestCheckpoint == nil {
		// Try to load from database
		checkpoints, err := s.loadCheckpointsFromDB(req.ThreadId, 1)
		if err != nil || len(checkpoints) == 0 {
			return nil, status.Error(codes.NotFound, "no checkpoints found for thread")
		}
		latestCheckpoint = checkpoints[0]
	}

	return &proto.GetCheckpointResponse{
		Success:    true,
		Checkpoint: latestCheckpoint,
	}, nil
}

// CleanupCheckpoints removes old checkpoints
func (s *CheckpointServer) CleanupCheckpoints(ctx context.Context, req *proto.CleanupCheckpointsRequest) (*proto.CleanupCheckpointsResponse, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	var deletedIDs []string
	var deletedCount int32

	// Filter checkpoints to delete
	var toDelete []string
	for id, cp := range s.checkpoints {
		// Check thread filter
		if req.ThreadId != "" && cp.ThreadId != req.ThreadId {
			continue
		}

		// Check age
		if req.OlderThanDays > 0 {
			age := time.Since(time.Unix(0, cp.CheckpointNs))
			if age.Hours()/24 < float64(req.OlderThanDays) {
				continue
			}
		}

		toDelete = append(toDelete, id)
	}

	// Keep N most recent checkpoints
	if req.KeepCount > 0 {
		// Sort by timestamp
		var sorted []*proto.Checkpoint
		for _, id := range toDelete {
			if cp, ok := s.checkpoints[id]; ok {
				sorted = append(sorted, cp)
			}
		}
		for i := 0; i < len(sorted)-1; i++ {
			for j := i + 1; j < len(sorted); j++ {
				if sorted[j].CheckpointNs > sorted[i].CheckpointNs {
					sorted[i], sorted[j] = sorted[j], sorted[i]
				}
			}
		}

		// Keep only the most recent ones
		if len(sorted) > int(req.KeepCount) {
			for _, cp := range sorted[:len(sorted)-int(req.KeepCount)] {
				toDelete = append(toDelete, cp.Id)
			}
		}
	}

	// Delete checkpoints
	for _, id := range toDelete {
		if _, ok := s.checkpoints[id]; ok {
			delete(s.checkpoints, id)
			deletedIDs = append(deletedIDs, id)
			deletedCount++
		}
	}

	// Log cleanup
	s.logger.Printf("Checkpoint cleanup: deleted %d checkpoints", deletedCount)

	return &proto.CleanupCheckpointsResponse{
		Success:     true,
		DeletedCount: deletedCount,
		DeletedIds:  deletedIDs,
	}, nil
}

// SubscribeCheckpoints subscribes to checkpoint events for a thread
func (s *CheckpointServer) SubscribeCheckpoints(req *proto.SubscribeCheckpointsRequest, stream proto.CheckpointService_SubscribeCheckpointsServer) error {
	s.mu.Lock()

	// Create event channel for this subscription
	eventChan := make(chan *proto.CheckpointEvent, 100)
	threadID := req.ThreadId
	if threadID == "" {
		threadID = "all" // Subscribe to all threads
	}
	s.checkpointSub[threadID] = eventChan

	// Send historical events if requested
	if req.IncludeHistory {
		s.mu.RLock()
		for _, cp := range s.checkpoints {
			if req.ThreadId == "" || cp.ThreadId == req.ThreadId {
				event := &proto.CheckpointEvent{
					CheckpointId: cp.Id,
					ThreadId:     cp.ThreadId,
					EventType:    proto.CheckpointEventType_CHECKPOINT_EVENT_CREATED,
					Timestamp:    cp.CreatedAt,
					Checkpoint:   cp,
				}
				if err := stream.Send(event); err != nil {
					s.mu.RUnlock()
					return err
				}
			}
		}
		s.mu.RUnlock()
	}

	s.mu.Unlock()

	// Wait for new events
	for {
		select {
		case <-stream.Context().Done():
			// Client disconnected
			s.mu.Lock()
			delete(s.checkpointSub, threadID)
			s.mu.Unlock()
			return nil
		case event, ok := <-eventChan:
			if !ok {
				// Channel closed
				s.mu.Lock()
				delete(s.checkpointSub, threadID)
				s.mu.Unlock()
				return nil
			}
			if err := stream.Send(event); err != nil {
				return err
			}
		}
	}
}

// HealthCheck returns the health status of the checkpoint server
func (s *CheckpointServer) HealthCheck(ctx context.Context, req *proto.CheckpointHealthRequest) (*proto.CheckpointHealthResponse, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	// Calculate statistics
	totalCheckpoints := int64(len(s.checkpoints))
	var totalSizeBytes int64
	for _, cp := range s.checkpoints {
		totalSizeBytes += int64(len(cp.StateBlob) + len(cp.ChannelValues) + len(cp.PendingSends))
	}

	return &proto.CheckpointHealthResponse{
		Healthy:          true,
		TotalCheckpoints: totalCheckpoints,
		TotalSizeBytes:   totalSizeBytes,
		MigrationStatus: &proto.MigrationStatus{
			CurrentVersion:      "1.0.0",
			AppliedMigrations:   []string{"initial_schema"},
			PendingMigrations:   []string{},
			MigrationRequired:   false,
		},
	}, nil
}

// saveCheckpointToDB saves a checkpoint to the database
func (s *CheckpointServer) saveCheckpointToDB(cp *proto.Checkpoint) error {
	// Serialize checkpoint metadata to JSON
	metadataJSON, err := json.Marshal(map[string]interface{}{
		"checkpoint_type": cp.CheckpointType.String(),
		"parent_ids":      cp.ParentIds,
		"metadata":        cp.Metadata,
	})
	if err != nil {
		return fmt.Errorf("failed to marshal checkpoint metadata: %w", err)
	}

	_, err = s.db.conn.Exec(
		`INSERT INTO checkpoints (id, thread_id, checkpoint_ns, checkpoint_type, created_at, updated_at, state_blob, channel_values, pending_sends, parent_ids, metadata, task_id)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		cp.Id, cp.ThreadId, cp.CheckpointNs, cp.CheckpointType.String(),
		cp.CreatedAt.AsTime(), cp.UpdatedAt.AsTime(),
		cp.StateBlob, cp.ChannelValues, cp.PendingSends, cp.ParentIds,
		string(metadataJSON), cp.TaskId,
	)
	if err != nil {
		return fmt.Errorf("failed to save checkpoint: %w", err)
	}

	return nil
}

// loadCheckpointFromDB loads a checkpoint from the database
func (s *CheckpointServer) loadCheckpointFromDB(checkpointID string) (*proto.Checkpoint, error) {
	var (
		id, threadID, checkpointType, stateBlob, channelValues, pendingSends, parentIDs, metadata, taskID string
		checkpointNs                                                                                       int64
		createdAt, updatedAt                                                                               time.Time
	)

	err := s.db.conn.QueryRow(
		`SELECT id, thread_id, checkpoint_ns, checkpoint_type, created_at, updated_at, state_blob, channel_values, pending_sends, parent_ids, metadata, task_id
		 FROM checkpoints WHERE id = ?`,
		checkpointID,
	).Scan(&id, &threadID, &checkpointNs, &checkpointType, &createdAt, &updatedAt,
		&stateBlob, &channelValues, &pendingSends, &parentIDs, &metadata, &taskID)
	if err != nil {
		return nil, fmt.Errorf("failed to query checkpoint: %w", err)
	}

	// Parse metadata
	var metadataMap map[string]interface{}
	if err := json.Unmarshal([]byte(metadata), &metadataMap); err != nil {
		return nil, fmt.Errorf("failed to unmarshal metadata: %w", err)
	}

	// Parse parent IDs
	var parentIDsList []string
	if parentIDs != "" {
		if err := json.Unmarshal([]byte(parentIDs), &parentIDsList); err != nil {
			return nil, fmt.Errorf("failed to unmarshal parent IDs: %w", err)
		}
	}

	return &proto.Checkpoint{
		Id:             id,
		ThreadId:       threadID,
		CheckpointNs:   checkpointNs,
		CheckpointType: convertCheckpointType(checkpointType),
		CreatedAt:      timestamppb.New(createdAt),
		UpdatedAt:      timestamppb.New(updatedAt),
		StateBlob:      []byte(stateBlob),
		ChannelValues:  []byte(channelValues),
		PendingSends:   []byte(pendingSends),
		ParentIds:      parentIDsList,
		Metadata:       metadata,
		TaskId:         taskID,
	}, nil
}

// loadCheckpointsFromDB loads multiple checkpoints from the database
func (s *CheckpointServer) loadCheckpointsFromDB(threadID string, limit int) ([]*proto.Checkpoint, error) {
	rows, err := s.db.conn.Query(
		`SELECT id, thread_id, checkpoint_ns, checkpoint_type, created_at, updated_at, state_blob, channel_values, pending_sends, parent_ids, metadata, task_id
		 FROM checkpoints WHERE thread_id = ? ORDER BY checkpoint_ns DESC LIMIT ?`,
		threadID, limit,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to query checkpoints: %w", err)
	}
	defer rows.Close()

	var checkpoints []*proto.Checkpoint
	for rows.Next() {
		var (
			id, threadID, checkpointType, stateBlob, channelValues, pendingSends, parentIDs, metadata, taskID string
			checkpointNs                                                                                       int64
			createdAt, updatedAt                                                                               time.Time
		)

		err := rows.Scan(&id, &threadID, &checkpointNs, &checkpointType, &createdAt, &updatedAt,
			&stateBlob, &channelValues, &pendingSends, &parentIDs, &metadata, &taskID)
		if err != nil {
			return nil, fmt.Errorf("failed to scan checkpoint: %w", err)
		}

		// Parse metadata
		var metadataMap map[string]interface{}
		if err := json.Unmarshal([]byte(metadata), &metadataMap); err != nil {
			return nil, fmt.Errorf("failed to unmarshal metadata: %w", err)
		}

		// Parse parent IDs
		var parentIDsList []string
		if parentIDs != "" {
			if err := json.Unmarshal([]byte(parentIDs), &parentIDsList); err != nil {
				return nil, fmt.Errorf("failed to unmarshal parent IDs: %w", err)
			}
		}

		checkpoint := &proto.Checkpoint{
			Id:             id,
			ThreadId:       threadID,
			CheckpointNs:   checkpointNs,
			CheckpointType: convertCheckpointType(checkpointType),
			CreatedAt:      timestamppb.New(createdAt),
			UpdatedAt:      timestamppb.New(updatedAt),
			StateBlob:      []byte(stateBlob),
			ChannelValues:  []byte(channelValues),
			PendingSends:   []byte(pendingSends),
			ParentIds:      parentIDsList,
			Metadata:       metadata,
			TaskId:         taskID,
		}
		checkpoints = append(checkpoints, checkpoint)
	}

	return checkpoints, nil
}

// convertCheckpointType converts string checkpoint type to protobuf CheckpointType
func convertCheckpointType(checkpointType string) proto.CheckpointType {
	switch checkpointType {
	case "CHECKPOINT_TYPE_LOCAL":
		return proto.CheckpointType_CHECKPOINT_TYPE_LOCAL
	case "CHECKPOINT_TYPE_MEMORY":
		return proto.CheckpointType_CHECKPOINT_TYPE_MEMORY
	default:
		return proto.CheckpointType_CHECKPOINT_TYPE_UNSPECIFIED
	}
}

// StartGRPC starts the gRPC server for the checkpoint service
func (s *CheckpointServer) StartGRPC(port int) error {
	s.port = port
	addr := fmt.Sprintf(":%d", port)

	// Create gRPC server
	grpcServer := grpc.NewServer()

	// Register checkpoint service
	proto.RegisterCheckpointServiceServer(grpcServer, s)

	s.grpcServer = grpcServer

	// Start gRPC server in goroutine
	go func() {
		listener, err := net.Listen("tcp", addr)
		if err != nil {
			s.logger.Printf("Failed to start checkpoint gRPC server on port %d: %v", port, err)
			return
		}
		s.logger.Printf("Checkpoint gRPC server starting on port %d", port)
		if err := grpcServer.Serve(listener); err != nil {
			s.logger.Printf("Checkpoint gRPC server error: %v", err)
		}
	}()

	// Wait for server to be ready
	time.Sleep(100 * time.Millisecond)

	return nil
}

// StopGRPC stops the gRPC server
func (s *CheckpointServer) StopGRPC() error {
	if s.grpcServer != nil {
		s.grpcServer.GracefulStop()
		s.logger.Printf("Checkpoint gRPC server stopped")
	}
	return nil
}

// GetPort returns the gRPC server port
func (s *CheckpointServer) GetPort() int {
	return s.port
}
