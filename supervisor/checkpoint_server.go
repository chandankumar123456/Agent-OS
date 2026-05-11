package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"sync"
	"time"

	"github.com/AgentOS/supervisor/logger"
	cp "github.com/AgentOS/supervisor/proto/checkpoint"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"
)

// CheckpointServer implements the CheckpointServiceServer interface
type CheckpointServer struct {
	cp.UnimplementedCheckpointServiceServer
	mu            sync.RWMutex
	checkpoints   map[string]*cp.Checkpoint
	checkpointSub map[string]chan *cp.CheckpointEvent
	db            *DB
	logger        *logger.Logger
	grpcServer    *grpc.Server
	running       bool
	port          int
	authKey       string // API key for local auth
}

// SetAuthKey sets the API key for gRPC auth
func (s *CheckpointServer) SetAuthKey(key string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.authKey = key
}

// NewCheckpointServer creates a new checkpoint server
func NewCheckpointServer(db *DB, logger *logger.Logger) *CheckpointServer {
	return &CheckpointServer{
		checkpoints:   make(map[string]*cp.Checkpoint),
		checkpointSub: make(map[string]chan *cp.CheckpointEvent),
		db:            db,
		logger:        logger,
	}
}

// SaveCheckpoint saves a checkpoint to the database
func (s *CheckpointServer) SaveCheckpoint(ctx context.Context, req *cp.SaveCheckpointRequest) (*cp.SaveCheckpointResponse, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	// Generate unique checkpoint ID
	checkpointID := fmt.Sprintf("checkpoint_%d", time.Now().UnixNano())

	// Create checkpoint
	checkpoint := &cp.Checkpoint{
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
	event := &cp.CheckpointEvent{
		CheckpointId: checkpointID,
		ThreadId:     req.ThreadId,
		EventType:    cp.CheckpointEventType_CHECKPOINT_EVENT_CREATED,
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
		s.logger.Infof("Warning: Failed to save checkpoint to database: %v", err)
	}

	return &cp.SaveCheckpointResponse{
		Success:      true,
		CheckpointId: checkpointID,
	}, nil
}

// GetCheckpoint retrieves a checkpoint by ID
func (s *CheckpointServer) GetCheckpoint(ctx context.Context, req *cp.GetCheckpointRequest) (*cp.GetCheckpointResponse, error) {
	s.mu.RLock()
	checkpoint, ok := s.checkpoints[req.CheckpointId]
	s.mu.RUnlock()

	if !ok {
		// Try to load from database
		checkpoint, err := s.loadCheckpointFromDB(req.CheckpointId)
		if err != nil {
			return nil, status.Error(codes.NotFound, "checkpoint not found")
		}
		return &cp.GetCheckpointResponse{
			Success:  true,
			Checkpoint: checkpoint,
		}, nil
	}

	return &cp.GetCheckpointResponse{
		Success:    true,
		Checkpoint: checkpoint,
	}, nil
}

// ListCheckpoints lists checkpoints for a thread with pagination
func (s *CheckpointServer) ListCheckpoints(ctx context.Context, req *cp.ListCheckpointsRequest) (*cp.ListCheckpointsResponse, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	var checkpoints []*cp.Checkpoint
	for _, ckpt := range s.checkpoints {
		if ckpt.ThreadId == req.ThreadId {
			checkpoints = append(checkpoints, ckpt)
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
		checkpoints = []*cp.Checkpoint{}
	} else {
		end := start + int(req.Limit)
		if end > len(checkpoints) {
			end = len(checkpoints)
		}
		checkpoints = checkpoints[start:end]
	}

	return &cp.ListCheckpointsResponse{
		Success:     true,
		Checkpoints: checkpoints,
		TotalCount:  int32(len(checkpoints)),
	}, nil
}

// GetLatestCheckpoint gets the most recent checkpoint for a thread
func (s *CheckpointServer) GetLatestCheckpoint(ctx context.Context, req *cp.GetLatestCheckpointRequest) (*cp.GetCheckpointResponse, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	var latestCheckpoint *cp.Checkpoint
	var latestTime int64 = -1

	for _, ckpt := range s.checkpoints {
		if ckpt.ThreadId == req.ThreadId && ckpt.CheckpointNs > latestTime {
			latestTime = ckpt.CheckpointNs
			latestCheckpoint = ckpt
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

	return &cp.GetCheckpointResponse{
		Success:    true,
		Checkpoint: latestCheckpoint,
	}, nil
}

// CleanupCheckpoints removes old checkpoints
func (s *CheckpointServer) CleanupCheckpoints(ctx context.Context, req *cp.CleanupCheckpointsRequest) (*cp.CleanupCheckpointsResponse, error) {
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
		var sorted []*cp.Checkpoint
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
			for _, ckpt := range sorted[:len(sorted)-int(req.KeepCount)] {
				toDelete = append(toDelete, ckpt.Id)
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
	s.logger.Infof("Checkpoint cleanup: deleted %d checkpoints", deletedCount)

	return &cp.CleanupCheckpointsResponse{
		Success:     true,
		DeletedCount: deletedCount,
		DeletedIds:  deletedIDs,
	}, nil
}

// SubscribeCheckpoints subscribes to checkpoint events for a thread
func (s *CheckpointServer) SubscribeCheckpoints(req *cp.SubscribeCheckpointsRequest, stream cp.CheckpointService_SubscribeCheckpointsServer) error {
	s.mu.Lock()

	// Create event channel for this subscription
	eventChan := make(chan *cp.CheckpointEvent, 100)
	threadID := req.ThreadId
	if threadID == "" {
		threadID = "all" // Subscribe to all threads
	}
	s.checkpointSub[threadID] = eventChan

	// Send historical events if requested
	if req.IncludeHistory {
		s.mu.RLock()
		for _, ckpt := range s.checkpoints {
			if req.ThreadId == "" || ckpt.ThreadId == req.ThreadId {
				event := &cp.CheckpointEvent{
					CheckpointId: ckpt.Id,
					ThreadId:     ckpt.ThreadId,
					EventType:    cp.CheckpointEventType_CHECKPOINT_EVENT_CREATED,
					Timestamp:    ckpt.CreatedAt,
					Checkpoint:   ckpt,
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
func (s *CheckpointServer) HealthCheck(ctx context.Context, req *cp.CheckpointHealthRequest) (*cp.CheckpointHealthResponse, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	// Calculate statistics
	totalCheckpoints := int64(len(s.checkpoints))
	var totalSizeBytes int64
	for _, ckpt := range s.checkpoints {
		totalSizeBytes += int64(len(ckpt.StateBlob) + len(ckpt.ChannelValues) + len(ckpt.PendingSends))
	}

	return &cp.CheckpointHealthResponse{
		Healthy:          true,
		TotalCheckpoints: totalCheckpoints,
		TotalSizeBytes:   totalSizeBytes,
		MigrationStatus: &cp.MigrationStatus{
			CurrentVersion:      "1.0.0",
			AppliedMigrations:   []string{"initial_schema"},
			PendingMigrations:   []string{},
			MigrationRequired:   false,
		},
	}, nil
}

// saveCheckpointToDB saves a checkpoint to the database
func (s *CheckpointServer) saveCheckpointToDB(cp *cp.Checkpoint) error {
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
func (s *CheckpointServer) loadCheckpointFromDB(checkpointID string) (*cp.Checkpoint, error) {
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

	return &cp.Checkpoint{
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
func (s *CheckpointServer) loadCheckpointsFromDB(threadID string, limit int) ([]*cp.Checkpoint, error) {
	rows, err := s.db.conn.Query(
		`SELECT id, thread_id, checkpoint_ns, checkpoint_type, created_at, updated_at, state_blob, channel_values, pending_sends, parent_ids, metadata, task_id
		 FROM checkpoints WHERE thread_id = ? ORDER BY checkpoint_ns DESC LIMIT ?`,
		threadID, limit,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to query checkpoints: %w", err)
	}
	defer rows.Close()

	var checkpoints []*cp.Checkpoint
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

		checkpoint := &cp.Checkpoint{
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
func convertCheckpointType(checkpointType string) cp.CheckpointType {
	switch checkpointType {
	case "CHECKPOINT_TYPE_LOCAL":
		return cp.CheckpointType_CHECKPOINT_TYPE_LOCAL
	case "CHECKPOINT_TYPE_MEMORY":
		return cp.CheckpointType_CHECKPOINT_TYPE_MEMORY
	default:
		return cp.CheckpointType_CHECKPOINT_TYPE_UNSPECIFIED
	}
}

// StartGRPC starts the gRPC server for the checkpoint service with TLS + API key auth
func (s *CheckpointServer) StartGRPC(port int, cryptoMgr *CryptoManager) error {
	s.port = port
	addr := fmt.Sprintf("127.0.0.1:%d", port)

	// Load TLS config
	tlsConfig, err := cryptoMgr.GetServerTLSConfig()
	if err != nil {
		return fmt.Errorf("failed to load TLS config: %w", err)
	}
	cred := credentials.NewTLS(tlsConfig)

	// Create auth interceptor
	authInterceptor := func(ctx context.Context, req interface{}, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (interface{}, error) {
		md, ok := metadata.FromIncomingContext(ctx)
		if !ok {
			return nil, status.Error(codes.Unauthenticated, "missing metadata")
		}
		keys := md.Get("x-api-key")
		if len(keys) == 0 || keys[0] != s.authKey {
			return nil, status.Error(codes.Unauthenticated, "invalid API key")
		}
		return handler(ctx, req)
	}

	// Create gRPC server with TLS and auth
	grpcServer := grpc.NewServer(
		grpc.Creds(cred),
		grpc.UnaryInterceptor(authInterceptor),
	)

	// Register checkpoint service
	cp.RegisterCheckpointServiceServer(grpcServer, s)

	s.grpcServer = grpcServer
	s.running = true

	// Start gRPC server in goroutine
	go func() {
		listener, err := net.Listen("tcp", addr)
		if err != nil {
			s.logger.Infof("Failed to start checkpoint gRPC server on port %d: %v", port, err)
			s.mu.Lock()
			s.running = false
			s.mu.Unlock()
			return
		}
		s.logger.Infof("Checkpoint gRPC server starting on %s with TLS + auth", addr)
		if err := grpcServer.Serve(listener); err != nil {
			s.logger.Infof("Checkpoint gRPC server error: %v", err)
		}
		s.mu.Lock()
		s.running = false
		s.mu.Unlock()
	}()

	// Wait for server to be ready
	time.Sleep(100 * time.Millisecond)

	return nil
}

// StopGRPC stops the gRPC server
func (s *CheckpointServer) StopGRPC() error {
	if s.grpcServer != nil {
		s.grpcServer.GracefulStop()
		s.running = false
		s.logger.Infof("Checkpoint gRPC server stopped")
	}
	return nil
}

// GetPort returns the gRPC server port
func (s *CheckpointServer) GetPort() int {
	return s.port
}

// IsHealthy returns whether the gRPC server is running
func (s *CheckpointServer) IsHealthy() bool {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.running
}
