package main

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
	"time"

	"github.com/AgentOS/supervisor/proto/runtime"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"
)

// RuntimeServer implements the RuntimeServiceServer interface
type RuntimeServer struct {
	runtime.UnimplementedRuntimeServiceServer
	mu           sync.RWMutex
	tasks        map[string]*runtime.Task
	taskEvents   map[string][]*runtime.TaskEvent
	taskEventSub map[string]chan *runtime.TaskEvent
	db           *DB
	logger       *log.Logger
}

// NewRuntimeServer creates a new runtime server
func NewRuntimeServer(db *DB, logger *log.Logger) *RuntimeServer {
	return &RuntimeServer{
		tasks:        make(map[string]*runtime.Task),
		taskEvents:   make(map[string][]*runtime.TaskEvent),
		taskEventSub: make(map[string]chan *runtime.TaskEvent),
		db:           db,
		logger:       logger,
	}
}

// CreateTask creates a new task
func (s *RuntimeServer) CreateTask(ctx context.Context, req *runtime.CreateTaskRequest) (*runtime.CreateTaskResponse, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	taskID := req.Query
	if taskID == "" {
		return nil, status.Error(codes.InvalidArgument, "query cannot be empty")
	}

	// Generate unique task ID
	taskID = fmt.Sprintf("task_%d", time.Now().UnixNano())

	// Create task
	task := &runtime.Task{
		Id:         taskID,
		Query:      req.Query,
		Status:     runtime.TaskStatus_TASK_STATUS_PENDING,
		Type:       req.Type,
		CreatedAt:  timestamppb.Now(),
		UpdatedAt:  timestamppb.Now(),
		Progress:   0,
		Metadata:   req.Config,
	}

	// Store task
	s.tasks[taskID] = task

	// Create event
	event := &runtime.TaskEvent{
		TaskId:     taskID,
		EventType:  runtime.TaskEventType_TASK_EVENT_CREATED,
		Timestamp:  timestamppb.Now(),
		Task:       task,
	}

	// Store event
	s.taskEvents[taskID] = append(s.taskEvents[taskID], event)

	// Notify subscribers
	if ch, ok := s.taskEventSub[taskID]; ok {
		select {
		case ch <- event:
		default:
			// Subscriber not ready, skip
		}
	}

	// Save to database
	if err := s.saveTaskToDB(task); err != nil {
		s.logger.Printf("Warning: Failed to save task to database: %v", err)
	}

	return &runtime.CreateTaskResponse{
		Success: true,
		Task:    task,
	}, nil
}

// GetTask retrieves a task by ID
func (s *RuntimeServer) GetTask(ctx context.Context, req *runtime.GetTaskRequest) (*runtime.GetTaskResponse, error) {
	s.mu.RLock()
	task, ok := s.tasks[req.TaskId]
	s.mu.RUnlock()

	if !ok {
		return nil, status.Error(codes.NotFound, "task not found")
	}

	// Get steps from database
	steps, err := s.getStepsFromDB(req.TaskId)
	if err != nil {
		s.logger.Printf("Warning: Failed to get steps from database: %v", err)
	}

	return &runtime.GetTaskResponse{
		Success: true,
		Task:    task,
		Steps:   steps,
	}, nil
}

// CancelTask cancels a task
func (s *RuntimeServer) CancelTask(ctx context.Context, req *runtime.CancelTaskRequest) (*runtime.CancelTaskResponse, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	task, ok := s.tasks[req.TaskId]
	if !ok {
		return nil, status.Error(codes.NotFound, "task not found")
	}

	task.Status = runtime.TaskStatus_TASK_STATUS_CANCELLED
	task.UpdatedAt = timestamppb.Now()
	task.Error = req.Reason

	// Update task
	s.tasks[req.TaskId] = task

	// Create event
	event := &runtime.TaskEvent{
		TaskId:     req.TaskId,
		EventType:  runtime.TaskEventType_TASK_EVENT_CANCELLED,
		Timestamp:  timestamppb.Now(),
		Task:       task,
		Error:      req.Reason,
	}

	// Store event
	s.taskEvents[req.TaskId] = append(s.taskEvents[req.TaskId], event)

	// Notify subscribers
	if ch, ok := s.taskEventSub[req.TaskId]; ok {
		select {
		case ch <- event:
		default:
			// Subscriber not ready, skip
		}
	}

	// Update database
	if err := s.updateTaskInDB(task); err != nil {
		s.logger.Printf("Warning: Failed to update task in database: %v", err)
	}

	return &runtime.CancelTaskResponse{
		Success: true,
	}, nil
}

// ListTasks lists tasks with optional filtering
func (s *RuntimeServer) ListTasks(ctx context.Context, req *runtime.ListTasksRequest) (*runtime.ListTasksResponse, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	var tasks []*runtime.Task
	for _, task := range s.tasks {
		if req.FilterStatus != runtime.TaskStatus_TASK_STATUS_UNSPECIFIED &&
			task.Status != req.FilterStatus {
			continue
		}
		if !req.IncludeCompleted &&
			(task.Status == runtime.TaskStatus_TASK_STATUS_COMPLETED ||
				task.Status == runtime.TaskStatus_TASK_STATUS_FAILED ||
				task.Status == runtime.TaskStatus_TASK_STATUS_CANCELLED) {
			continue
		}
		tasks = append(tasks, task)
	}

	// Apply pagination
	start := int(req.Offset)
	if start >= len(tasks) {
		tasks = []*runtime.Task{}
	} else {
		end := start + int(req.Limit)
		if end > len(tasks) {
			end = len(tasks)
		}
		tasks = tasks[start:end]
	}

	return &runtime.ListTasksResponse{
		Success:    true,
		Tasks:      tasks,
		TotalCount: int32(len(s.tasks)),
	}, nil
}

// StreamTaskEvents streams task events for a specific task
func (s *RuntimeServer) StreamTaskEvents(req *runtime.TaskEventRequest, stream runtime.RuntimeService_StreamTaskEventsServer) error {
	s.mu.Lock()

	// Create event channel for this subscription
	eventChan := make(chan *runtime.TaskEvent, 100)
	s.taskEventSub[req.TaskId] = eventChan

	// Send historical events if requested
	if req.IncludeHistory {
		events := s.taskEvents[req.TaskId]
		for _, event := range events {
			if err := stream.Send(event); err != nil {
				s.mu.Unlock()
				return err
			}
		}
	}

	s.mu.Unlock()

	// Wait for new events
	for {
		select {
		case <-stream.Context().Done():
			// Client disconnected
			s.mu.Lock()
			delete(s.taskEventSub, req.TaskId)
			s.mu.Unlock()
			return nil
		case event, ok := <-eventChan:
			if !ok {
				// Channel closed
				s.mu.Lock()
				delete(s.taskEventSub, req.TaskId)
				s.mu.Unlock()
				return nil
			}
			if err := stream.Send(event); err != nil {
				return err
			}
		}
	}
}

// GetRuntimeStatus returns the current runtime status
func (s *RuntimeServer) GetRuntimeStatus(ctx context.Context, req *runtime.GetRuntimeStatusRequest) (*runtime.RuntimeStatus, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	// Calculate statistics
	var activeTasks, queuedTasks, completedTasks, failedTasks int32
	for _, task := range s.tasks {
		switch task.Status {
		case runtime.TaskStatus_TASK_STATUS_PENDING,
			runtime.TaskStatus_TASK_STATUS_PLANNING,
			runtime.TaskStatus_TASK_STATUS_EXECUTING,
			runtime.TaskStatus_TASK_STATUS_VERIFYING,
			runtime.TaskStatus_TASK_STATUS_AWAITING_APPROVAL:
			activeTasks++
		case runtime.TaskStatus_TASK_STATUS_COMPLETED:
			completedTasks++
		case runtime.TaskStatus_TASK_STATUS_FAILED,
			runtime.TaskStatus_TASK_STATUS_CANCELLED:
			failedTasks++
		default:
			queuedTasks++
		}
	}

	return &runtime.RuntimeStatus{
		Version:      "0.1.0",
		State:        runtime.RuntimeState_RUNTIME_STATE_READY,
		ActiveTasks:  activeTasks,
		QueuedTasks:  queuedTasks,
		CompletedTasks: completedTasks,
		FailedTasks:  failedTasks,
		Metrics: &runtime.RuntimeMetrics{
			CpuPercent:         0.0,
			MemoryBytes:        0,
			AvgTaskDurationMs:  0,
			TaskSuccessRate:    100,
			TotalToolCalls:     0,
		},
		Uptime:    timestamppb.Now(),
		Config:    map[string]string{"version": "0.1.0"},
	}, nil
}

// Shutdown gracefully shuts down the runtime server
func (s *RuntimeServer) Shutdown(ctx context.Context, req *runtime.ShutdownRequest) (*runtime.ShutdownResponse, error) {
	s.logger.Printf("Runtime server shutdown requested")

	// Wait for active tasks to complete
	if req.Graceful {
		timeout := time.Duration(req.TimeoutSeconds) * time.Second
		ctx, cancel := context.WithTimeout(context.Background(), timeout)
		defer cancel()

		// Wait for tasks to complete
		ticker := time.NewTicker(100 * time.Millisecond)
		defer ticker.Stop()

		for {
			select {
			case <-ctx.Done():
				s.logger.Printf("Graceful shutdown timed out")
				return &runtime.ShutdownResponse{
					Success: true,
					Message: "Graceful shutdown timed out, forcing shutdown",
				}, nil
			default:
				s.mu.RLock()
				active := 0
				for _, task := range s.tasks {
					if task.Status == runtime.TaskStatus_TASK_STATUS_EXECUTING ||
						task.Status == runtime.TaskStatus_TASK_STATUS_PLANNING {
						active++
					}
				}
				s.mu.RUnlock()

				if active == 0 {
					s.logger.Printf("All tasks completed, shutting down")
					return &runtime.ShutdownResponse{
						Success: true,
						Message: "Graceful shutdown complete",
					}, nil
				}
				<-ticker.C
			}
		}
	}

	return &runtime.ShutdownResponse{
		Success: true,
		Message: "Forced shutdown",
	}, nil
}

// HealthCheck returns the health status of the runtime server
func (s *RuntimeServer) HealthCheck(ctx context.Context, req *runtime.HealthCheckRequest) (*runtime.HealthCheckResponse, error) {
	return &runtime.HealthCheckResponse{
		Healthy:   true,
		Version:   "0.1.0",
		Timestamp: timestamppb.Now(),
	}, nil
}

// GetConfig returns the current configuration
func (s *RuntimeServer) GetConfig(ctx context.Context, req *runtime.GetConfigRequest) (*runtime.GetConfigResponse, error) {
	config := map[string]string{
		"version":        "0.1.0",
		"runtime_state":  "ready",
		"max_concurrent": "100",
	}

	if req.Key != "" {
		if value, ok := config[req.Key]; ok {
			config = map[string]string{req.Key: value}
		} else {
			return &runtime.GetConfigResponse{
				Success: false,
				Error:   "key not found",
			}, nil
		}
	}

	return &runtime.GetConfigResponse{
		Success: true,
		Config:  config,
	}, nil
}

// SetConfig sets a configuration value
func (s *RuntimeServer) SetConfig(ctx context.Context, req *runtime.SetConfigRequest) (*runtime.SetConfigResponse, error) {
	// Configuration is read-only for now
	return &runtime.SetConfigResponse{
		Success: false,
		Error:   "configuration is read-only",
	}, nil
}

// saveTaskToDB saves a task to the database
func (s *RuntimeServer) saveTaskToDB(task *runtime.Task) error {
	// Serialize task to JSON
	taskJSON, err := json.Marshal(task)
	if err != nil {
		return fmt.Errorf("failed to marshal task: %w", err)
	}

	_, err = s.db.conn.Exec(
		`INSERT INTO agent_sessions (id, agent_id, status, input, output, started_at, created_at, updated_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
		task.Id, "runtime", task.Status.String(), task.Query, string(taskJSON),
		task.StartedAt.AsTime(), task.CreatedAt.AsTime(), task.UpdatedAt.AsTime(),
	)
	if err != nil {
		return fmt.Errorf("failed to save task: %w", err)
	}

	return nil
}

// updateTaskInDB updates a task in the database
func (s *RuntimeServer) updateTaskInDB(task *runtime.Task) error {
	// Serialize task to JSON
	taskJSON, err := json.Marshal(task)
	if err != nil {
		return fmt.Errorf("failed to marshal task: %w", err)
	}

	_, err = s.db.conn.Exec(
		`UPDATE agent_sessions SET status = ?, output = ?, error_message = ?, completed_at = ?, updated_at = ?
		 WHERE id = ?`,
		task.Status.String(), string(taskJSON), task.Error,
		task.CompletedAt.AsTime(), task.UpdatedAt.AsTime(), task.Id,
	)
	if err != nil {
		return fmt.Errorf("failed to update task: %w", err)
	}

	return nil
}

// getStepsFromDB retrieves steps for a task from the database
func (s *RuntimeServer) getStepsFromDB(taskID string) ([]*runtime.Step, error) {
	rows, err := s.db.conn.Query(
		`SELECT id, session_id, sequence, action_type, target, arguments, status, result, error_message, created_at
		 FROM actions WHERE session_id = ? ORDER BY sequence`,
		taskID,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to query steps: %w", err)
	}
	defer rows.Close()

	var steps []*runtime.Step
	for rows.Next() {
		var actionID, sessionID, actionType, target, arguments, status, result, errorMessage string
		var sequence int
		var createdAt time.Time

		err := rows.Scan(&actionID, &sessionID, &sequence, &actionType, &target,
			&arguments, &status, &result, &errorMessage, &createdAt)
		if err != nil {
			return nil, fmt.Errorf("failed to scan step: %w", err)
		}

		step := &runtime.Step{
			Index:     int32(sequence),
			ToolName:  actionType,
			ToolInput: arguments,
			ToolOutput: result,
			Status:    convertStepStatus(status),
			StartedAt: timestamppb.New(createdAt),
		}
		steps = append(steps, step)
	}

	return steps, nil
}

// convertStepStatus converts string status to protobuf StepStatus
func convertStepStatus(status string) runtime.StepStatus {
	switch status {
	case "pending":
		return runtime.StepStatus_STEP_STATUS_PENDING
	case "executing":
		return runtime.StepStatus_STEP_STATUS_EXECUTING
	case "completed":
		return runtime.StepStatus_STEP_STATUS_COMPLETED
	case "failed":
		return runtime.StepStatus_STEP_STATUS_FAILED
	case "skipped":
		return runtime.StepStatus_STEP_STATUS_SKIPPED
	default:
		return runtime.StepStatus_STEP_STATUS_UNSPECIFIED
	}
}
