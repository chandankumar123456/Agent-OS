package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"sync"
	"time"

	"github.com/AgentOS/supervisor/proto/runtime"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"
)

// ServerState represents the current state of the supervisor
type ServerState struct {
	Running     bool        `json:"running"`
	StartTime   time.Time   `json:"start_time"`
	PythonReady bool        `json:"python_ready"`
	GRPCReady   bool        `json:"grpc_ready"`
	GRPCPort    int         `json:"grpc_port"`
	MCPServers  []MCPStatus `json:"mcp_servers"`
}

// MCPStatus represents the status of an MCP server
type MCPStatus struct {
	Name     string `json:"name"`
	Running  bool   `json:"running"`
	Port     int    `json:"port"`
	LastPing string `json:"last_ping"`
}

// HealthResponse represents the health check response
type HealthResponse struct {
	Status     string            `json:"status"`
	Timestamp  time.Time         `json:"timestamp"`
	Version    string            `json:"version"`
	Components []ComponentStatus `json:"components"`
}

// ComponentStatus represents the status of a system component
type ComponentStatus struct {
	Name    string `json:"name"`
	Status  string `json:"status"`
	Message string `json:"message,omitempty"`
}

// Supervisor holds the supervisor state and services
type Supervisor struct {
	mu             sync.RWMutex
	state          ServerState
	pythonCmd      *exec.Cmd
	grpcCmd        *exec.Cmd
	executorCmd    *exec.Cmd // Python executor process
	mcpServers     map[string]*MCPStatus
	config         *Config
	db             *DB
	agentStore     *AgentSessionStore
	runtimeServer  *RuntimeServer  // gRPC runtime server
	checkpointServer *CheckpointServer // gRPC checkpoint server
	httpServer     *http.Server // HTTP server for graceful shutdown
	cryptoManager  *CryptoManager // TLS certificate manager
	apiKey         string // API key for local gRPC auth
	updater        *Updater // Auto-updater
	eventHub       *EventHub // WebSocket event hub
	grpcConn       *grpc.ClientConn             // gRPC connection to Python runtime
	grpcClient     runtime.RuntimeServiceClient  // gRPC client for Python runtime
}

// Metrics holds simple request metrics
type Metrics struct {
	TotalRequests     int64
	SuccessfulRequests int64
	FailedRequests    int64
	TotalLatency      time.Duration
}

// NewSupervisor creates a new supervisor instance
func NewSupervisor(config *Config) *Supervisor {
	return &Supervisor{
		state: ServerState{
			Running:   true,
			StartTime: time.Now(),
		},
		mcpServers: make(map[string]*MCPStatus),
		config:     config,
	}
}

// SetDB sets the database connection for the supervisor
func (s *Supervisor) SetDB(db *DB) {
	s.db = db
}

// SetEventHub sets the WebSocket event hub
func (s *Supervisor) SetEventHub(hub *EventHub) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.eventHub = hub
}

// SetCheckpointServer sets the checkpoint server
func (s *Supervisor) SetCheckpointServer(server *CheckpointServer) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.checkpointServer = server
}

// SetCryptoManager sets the crypto manager
func (s *Supervisor) SetCryptoManager(cm *CryptoManager) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.cryptoManager = cm
}

// SetAPIKey sets the API key for local auth
func (s *Supervisor) SetAPIKey(key string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.apiKey = key
}

// GetAPIKey returns the API key
func (s *Supervisor) GetAPIKey() string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.apiKey
}

// SetUpdater sets the updater
func (s *Supervisor) SetUpdater(updater *Updater) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.updater = updater
}

func (s *Supervisor) projectRoot() string {
	wd, err := os.Getwd()
	if err != nil {
		return ""
	}
	if _, err := os.Stat(filepath.Join(wd, "app")); err == nil {
		return wd
	}
	parent := filepath.Dir(wd)
	if _, err := os.Stat(filepath.Join(parent, "app")); err == nil {
		return parent
	}
	return ""
}

// Start starts the supervisor and its services
func (s *Supervisor) Start() error {
	s.mu.Lock()

	// Start Python runtime (desktop_entry starts its own gRPC server on port 50051)
	if err := s.startPythonRuntime(); err != nil {
		log.Printf("Warning: Failed to start Python runtime: %v", err)
	}

	// Separate gRPC server is no longer needed — desktop_entry handles it internally.
	// if err := s.startGRPCServer(); err != nil {
	// 	log.Printf("Warning: Failed to start gRPC server: %v", err)
	// }

	// Start checkpoint gRPC server
	if err := s.startCheckpointGRPCServer(); err != nil {
		log.Printf("Warning: Failed to start checkpoint gRPC server: %v", err)
	}

	// Start Python executor
	if err := s.startPythonExecutor(); err != nil {
		log.Printf("Warning: Failed to start Python executor: %v", err)
	}

	// Start MCP servers
	if err := s.startMCPServers(); err != nil {
		log.Printf("Warning: Failed to start MCP servers: %v", err)
	}

	s.mu.Unlock()

	// Connect gRPC client to Python runtime (retries take time, do outside lock)
	if err := s.connectGRPCClient(); err != nil {
		log.Printf("Warning: Failed to connect gRPC client: %v", err)
	}

	return nil
}

// startPythonRuntime starts the Python desktop-native runtime (includes its own gRPC server on port 50051)
func (s *Supervisor) startPythonRuntime() error {
	// Check if Python is available
	pythonPath, err := exec.LookPath("python")
	if err != nil {
		return err
	}

	cmd := exec.Command(pythonPath, "-m", "app.desktop_entry")
	cmd.Env = append(os.Environ(),
		"AGENTOS_RUNTIME_MODE=grpc",
		fmt.Sprintf("AGENTOS_API_KEY=%s", s.apiKey),
		fmt.Sprintf("AGENTOS_CERT_DIR=%s", filepath.Join(s.config.DataDir, "certs")),
	)
	if root := s.projectRoot(); root != "" {
		cmd.Dir = root
	}

	// Start the command
	if err := cmd.Start(); err != nil {
		return err
	}

	s.pythonCmd = cmd
	s.state.PythonReady = true

	log.Printf("Python runtime started on port 8000 (desktop_entry)")
	return nil
}

// connectGRPCClient establishes a gRPC client connection to the Python runtime with retries.
func (s *Supervisor) connectGRPCClient() error {
	var conn *grpc.ClientConn
	var lastErr error

	for i := 0; i < 10; i++ {
		conn, lastErr = grpc.Dial("localhost:50051", grpc.WithInsecure())
		if lastErr != nil {
			log.Printf("gRPC client connection attempt %d/10 failed: %v, retrying in 1s...", i+1, lastErr)
			time.Sleep(1 * time.Second)
			continue
		}

		// Test connection with health check
		client := runtime.NewRuntimeServiceClient(conn)
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		_, lastErr = client.HealthCheck(ctx, &runtime.HealthCheckRequest{})
		cancel()
		if lastErr == nil {
			s.mu.Lock()
			s.grpcConn = conn
			s.grpcClient = client
			s.state.GRPCReady = true
			s.state.GRPCPort = 50051
			s.mu.Unlock()
			log.Printf("gRPC client connected to Python runtime on port 50051")
			return nil
		}

		conn.Close()
		log.Printf("gRPC client health check attempt %d/10 failed: %v, retrying in 1s...", i+1, lastErr)
		time.Sleep(1 * time.Second)
	}

	return fmt.Errorf("failed to connect gRPC client after 10 attempts: %w", lastErr)
}

// stopPythonRuntime stops the Python FastAPI backend
func (s *Supervisor) stopPythonRuntime() error {
	if s.pythonCmd != nil && s.pythonCmd.Process != nil {
		return s.pythonCmd.Process.Kill()
	}
	return nil
}

// startGRPCServer starts the gRPC desktop automation server
func (s *Supervisor) startGRPCServer() error {
	// Check if Python is available (gRPC server is Python-based)
	pythonPath, err := exec.LookPath("python")
	if err != nil {
		return err
	}

	grpcPort := 50051
	cmd := exec.Command(pythonPath, "-m", "app.desktop.grpc_server")
	cmd.Env = append(os.Environ(),
		"GRPC_PORT=50051",
		fmt.Sprintf("AGENTOS_API_KEY=%s", s.apiKey),
		fmt.Sprintf("AGENTOS_CERT_DIR=%s", filepath.Join(s.config.DataDir, "certs")),
	)
	if root := s.projectRoot(); root != "" {
		cmd.Dir = root
	}

	// Start the command
	if err := cmd.Start(); err != nil {
		return err
	}

	s.grpcCmd = cmd
	s.state.GRPCReady = true
	s.state.GRPCPort = grpcPort

	log.Printf("gRPC desktop automation server started on port %d", grpcPort)
	return nil
}

// stopGRPCServer stops the gRPC desktop automation server
func (s *Supervisor) stopGRPCServer() error {
	if s.grpcCmd != nil && s.grpcCmd.Process != nil {
		if err := s.grpcCmd.Process.Kill(); err != nil {
			return err
		}
		s.state.GRPCReady = false
		log.Printf("gRPC server stopped")
	}
	return nil
}

// startCheckpointGRPCServer starts the checkpoint gRPC server
func (s *Supervisor) startCheckpointGRPCServer() error {
	if s.checkpointServer == nil {
		return fmt.Errorf("checkpoint server not initialized")
	}

	checkpointPort := 50052
	if err := s.checkpointServer.StartGRPC(checkpointPort, s.cryptoManager); err != nil {
		return fmt.Errorf("failed to start checkpoint gRPC server: %w", err)
	}

	s.state.Running = true
	log.Printf("Checkpoint gRPC server started on port %d with TLS + auth", checkpointPort)
	return nil
}

// stopCheckpointGRPCServer stops the checkpoint gRPC server
func (s *Supervisor) stopCheckpointGRPCServer() error {
	if s.checkpointServer != nil {
		if err := s.checkpointServer.StopGRPC(); err != nil {
			return err
		}
		log.Printf("Checkpoint gRPC server stopped")
	}
	return nil
}

// isCheckpointGRPCHealthy checks if the checkpoint gRPC server is responsive
func (s *Supervisor) isCheckpointGRPCHealthy() bool {
	if s.checkpointServer == nil {
		return false
	}
	return s.checkpointServer.IsHealthy()
}

// isGRPCHealthy checks if the gRPC client connection to Python runtime is healthy
func (s *Supervisor) isGRPCHealthy() bool {
	return s.state.GRPCReady && s.grpcClient != nil
}

// startMCPServers starts all MCP servers
func (s *Supervisor) startMCPServers() error {
	// Define MCP servers to start
	mcpConfigs := []struct {
		name string
		port int
	}{
		{"filesystem", 8001},
		{"shell", 8002},
		{"cloud_api", 8003},
		{"browser_env", 8004},
		{"desktop", 8005},
		{"document", 8006},
		{"code_executor", 8007},
	}

	for _, cfg := range mcpConfigs {
		status := &MCPStatus{
			Name: cfg.name,
			Port: cfg.port,
		}
		s.mcpServers[cfg.name] = status
	}

	log.Printf("MCP servers configured: %d", len(mcpConfigs))
	return nil
}

// stopMCPServers stops all MCP servers
func (s *Supervisor) stopMCPServers() error {
	// MCP servers are managed externally, just clear the state
	for name, status := range s.mcpServers {
		status.Running = false
		s.mcpServers[name] = status
	}
	return nil
}

// startPythonExecutor starts the Python executor server
func (s *Supervisor) startPythonExecutor() error {
	if !s.config.PythonExecutorEnabled {
		log.Printf("Python executor disabled, skipping startup")
		return nil
	}

	// Check if Python is available
	pythonPath, err := exec.LookPath("python")
	if err != nil {
		return fmt.Errorf("python not found: %w", err)
	}

	// Start Python executor as goroutine
	go func() {
		cmd := exec.Command(pythonPath, "-m", "app.workers.executor_server")
		cmd.Env = append(os.Environ(),
			fmt.Sprintf("EXECUTOR_ADDRESS=%s", s.config.PythonExecutorAddress),
			fmt.Sprintf("EXECUTOR_TIMEOUT=%d", s.config.PythonExecutorTimeout),
			fmt.Sprintf("AGENTOS_API_KEY=%s", s.apiKey),
			fmt.Sprintf("AGENTOS_CERT_DIR=%s", filepath.Join(s.config.DataDir, "certs")),
		)
		if root := s.projectRoot(); root != "" {
			cmd.Dir = root
		}

		// Store command reference
		s.mu.Lock()
		s.executorCmd = cmd
		s.mu.Unlock()

		// Start the command
		if err := cmd.Start(); err != nil {
			log.Printf("Failed to start Python executor: %v", err)
			return
		}

		log.Printf("Python executor started on %s", s.config.PythonExecutorAddress)

		// Wait for process to complete (or be killed)
		if err := cmd.Wait(); err != nil {
			log.Printf("Python executor exited: %v", err)
		}
	}()

	// Wait 2 seconds for readiness
	time.Sleep(2 * time.Second)

	return nil
}

// stopPythonExecutor stops the Python executor server
func (s *Supervisor) stopPythonExecutor() error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.executorCmd != nil && s.executorCmd.Process != nil {
		if err := s.executorCmd.Process.Kill(); err != nil {
			return fmt.Errorf("failed to kill Python executor: %w", err)
		}
		log.Printf("Python executor stopped")
	}
	return nil
}

// GetHealth returns the current health status
func (s *Supervisor) GetHealth() HealthResponse {
	s.mu.RLock()
	defer s.mu.RUnlock()

	grpcStatus := boolToStatus(s.isGRPCHealthy())
	grpcMessage := boolToMessage(s.isGRPCHealthy(), "gRPC server not running")

	components := []ComponentStatus{
		{
			Name:   "supervisor",
			Status: "healthy",
		},
		{
			Name:   "database",
			Status: "ready",
		},
		{
			Name:    "python_runtime",
			Status:  boolToStatus(s.state.PythonReady),
			Message: boolToMessage(s.state.PythonReady, "Python runtime not started"),
		},
		{
			Name:    "grpc_server",
			Status:  grpcStatus,
			Message: grpcMessage,
		},
	}

	for name, status := range s.mcpServers {
		components = append(components, ComponentStatus{
			Name:    name,
			Status:  boolToStatus(status.Running),
			Message: boolToMessage(status.Running, "MCP server not running"),
		})
	}

	return HealthResponse{
		Status:     "healthy",
		Timestamp:  time.Now(),
		Version:    "0.1.0",
		Components: components,
	}
}

// boolToStatus converts boolean to status string
func boolToStatus(b bool) string {
	if b {
		return "healthy"
	}
	return "unhealthy"
}

// boolToMessage converts boolean to message
func boolToMessage(b bool, falseMsg string) string {
	if b {
		return ""
	}
	return falseMsg
}

// HandleHealth handles health check requests
func (s *Supervisor) HandleHealth(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(s.GetHealth())
}

// HandleStatus handles status requests
func (s *Supervisor) HandleStatus(w http.ResponseWriter, r *http.Request) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	response := map[string]interface{}{
		"running":         s.state.Running,
		"start_time":      s.state.StartTime,
		"python_ready":    s.state.PythonReady,
		"python_port":     8000,
		"grpc_ready":      s.isGRPCHealthy(),
		"grpc_port":       s.state.GRPCPort,
		"supervisor_port": s.config.Port,
		"mcp_servers":     s.mcpServers,
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(response)
}

// HandleStartPython handles starting the Python runtime
func (s *Supervisor) HandleStartPython(w http.ResponseWriter, r *http.Request) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.state.PythonReady {
		w.WriteHeader(http.StatusConflict)
		json.NewEncoder(w).Encode(map[string]string{"message": "Python runtime already running"})
		return
	}

	if err := s.startPythonRuntime(); err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
		return
	}

	json.NewEncoder(w).Encode(map[string]string{"message": "Python runtime started"})
}

// HandleStopPython handles stopping the Python runtime
func (s *Supervisor) HandleStopPython(w http.ResponseWriter, r *http.Request) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if !s.state.PythonReady {
		w.WriteHeader(http.StatusConflict)
		json.NewEncoder(w).Encode(map[string]string{"message": "Python runtime not running"})
		return
	}

	if err := s.stopPythonRuntime(); err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
		return
	}

	s.state.PythonReady = false
	json.NewEncoder(w).Encode(map[string]string{"message": "Python runtime stopped"})
}

// HandleStartGRPC handles starting the gRPC server
func (s *Supervisor) HandleStartGRPC(w http.ResponseWriter, r *http.Request) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.isGRPCHealthy() {
		w.WriteHeader(http.StatusConflict)
		json.NewEncoder(w).Encode(map[string]string{"message": "gRPC server already running"})
		return
	}

	if err := s.startGRPCServer(); err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
		return
	}

	json.NewEncoder(w).Encode(map[string]interface{}{
		"message": "gRPC server started",
		"port":    s.state.GRPCPort,
	})
}

// HandleStopGRPC handles stopping the gRPC server
func (s *Supervisor) HandleStopGRPC(w http.ResponseWriter, r *http.Request) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if !s.isGRPCHealthy() {
		w.WriteHeader(http.StatusConflict)
		json.NewEncoder(w).Encode(map[string]string{"message": "gRPC server not running"})
		return
	}

	if err := s.stopGRPCServer(); err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
		return
	}

	s.state.GRPCReady = false
	json.NewEncoder(w).Encode(map[string]string{"message": "gRPC server stopped"})
}

// HandleGRPCHealth handles gRPC health check requests
func (s *Supervisor) HandleGRPCHealth(w http.ResponseWriter, r *http.Request) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	healthy := s.isGRPCHealthy()
	status := "healthy"
	if !healthy {
		status = "unhealthy"
	}

	response := map[string]interface{}{
		"status":     status,
		"grpc_ready": healthy,
		"grpc_port":  s.state.GRPCPort,
		"timestamp":  time.Now(),
	}

	if !healthy {
		w.WriteHeader(http.StatusServiceUnavailable)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(response)
}

// SetRuntimeServer sets the runtime server for task management
func (s *Supervisor) SetRuntimeServer(server *RuntimeServer) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.runtimeServer = server
}

// HandleTasksRoute routes task requests based on method and path
func (s *Supervisor) HandleTasksRoute(w http.ResponseWriter, r *http.Request) {
	path := r.URL.Path
	parts := splitPath(path)

	// Path patterns (after splitPath removes leading /):
	// POST   /api/v1/tasks              -> CreateTask (len=3, parts[2]="tasks")
	// GET    /api/v1/tasks              -> ListTasks  (len=3, parts[2]="tasks")
	// GET    /api/v1/tasks/{id}         -> GetTask    (len=4)
	// POST   /api/v1/tasks/{id}/cancel  -> CancelTask (len=5, parts[4]="cancel")

	switch r.Method {
	case http.MethodPost:
		if len(parts) >= 5 && parts[4] == "cancel" {
			s.HandleCancelTask(w, r)
		} else if len(parts) >= 5 && parts[4] == "approve" {
			s.HandleApproveTask(w, r)
		} else if len(parts) >= 5 && parts[4] == "reject" {
			s.HandleRejectTask(w, r)
		} else if len(parts) == 3 && parts[2] == "tasks" {
			s.HandleCreateTask(w, r)
		} else {
			w.WriteHeader(http.StatusNotFound)
			json.NewEncoder(w).Encode(map[string]string{"error": "not found"})
		}
	case http.MethodGet:
		if len(parts) >= 4 {
			s.HandleGetTask(w, r)
		} else if len(parts) == 3 && parts[2] == "tasks" {
			s.HandleListTasks(w, r)
		} else {
			w.WriteHeader(http.StatusNotFound)
			json.NewEncoder(w).Encode(map[string]string{"error": "not found"})
		}
	default:
		w.WriteHeader(http.StatusMethodNotAllowed)
		json.NewEncoder(w).Encode(map[string]string{"error": "method not allowed"})
	}
}

// HandleCreateTask handles POST /api/v1/tasks
func (s *Supervisor) HandleCreateTask(w http.ResponseWriter, r *http.Request) {
	s.mu.RLock()
	client := s.grpcClient
	s.mu.RUnlock()

	if client == nil {
		w.WriteHeader(http.StatusServiceUnavailable)
		json.NewEncoder(w).Encode(map[string]string{"error": "runtime server not initialized"})
		return
	}

	var req struct {
		Query string `json:"query"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{"error": "invalid request body: " + err.Error()})
		return
	}
	if req.Query == "" {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{"error": "query is required"})
		return
	}

	resp, err := client.CreateTask(r.Context(), &runtime.CreateTaskRequest{
		Query: req.Query,
		Type:  runtime.TaskType_TASK_TYPE_COMPLEX,
	})
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": "failed to create task: " + err.Error()})
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(map[string]interface{}{
		"task_id": resp.Task.Id,
		"status":  mapTaskStatus(resp.Task.Status),
	})
}

// HandleListTasks handles GET /api/v1/tasks
func (s *Supervisor) HandleListTasks(w http.ResponseWriter, r *http.Request) {
	s.mu.RLock()
	client := s.grpcClient
	s.mu.RUnlock()

	if client == nil {
		w.WriteHeader(http.StatusServiceUnavailable)
		json.NewEncoder(w).Encode(map[string]string{"error": "runtime server not initialized"})
		return
	}

	// Parse query params
	limit := int32(50)
	offset := int32(0)
	if l := r.URL.Query().Get("limit"); l != "" {
		if v, err := strconv.Atoi(l); err == nil {
			limit = int32(v)
		}
	}
	if o := r.URL.Query().Get("offset"); o != "" {
		if v, err := strconv.Atoi(o); err == nil {
			offset = int32(v)
		}
	}

	resp, err := client.ListTasks(r.Context(), &runtime.ListTasksRequest{
		Limit:  limit,
		Offset: offset,
	})
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": "failed to list tasks: " + err.Error()})
		return
	}

	tasks := make([]map[string]interface{}, 0, len(resp.Tasks))
	for _, task := range resp.Tasks {
		tasks = append(tasks, protoTaskToFullJSON(task, nil))
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"tasks": tasks,
		"total": int(resp.TotalCount),
	})
}

// HandleGetTask handles GET /api/v1/tasks/{id}
func (s *Supervisor) HandleGetTask(w http.ResponseWriter, r *http.Request) {
	s.mu.RLock()
	client := s.grpcClient
	s.mu.RUnlock()

	if client == nil {
		w.WriteHeader(http.StatusServiceUnavailable)
		json.NewEncoder(w).Encode(map[string]string{"error": "runtime server not initialized"})
		return
	}

	path := r.URL.Path
	parts := splitPath(path)
	if len(parts) < 4 {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{"error": "task ID is required"})
		return
	}
	taskID := parts[3]

	resp, err := client.GetTask(r.Context(), &runtime.GetTaskRequest{TaskId: taskID})
	if err != nil {
		if grpcStatus, ok := status.FromError(err); ok && grpcStatus.Code() == codes.NotFound {
			w.WriteHeader(http.StatusNotFound)
			json.NewEncoder(w).Encode(map[string]string{"error": "task not found"})
			return
		}
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": "failed to get task: " + err.Error()})
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(protoTaskToFullJSON(resp.Task, resp.Steps))
}

// HandleCancelTask handles POST /api/v1/tasks/{id}/cancel
func (s *Supervisor) HandleCancelTask(w http.ResponseWriter, r *http.Request) {
	s.mu.RLock()
	client := s.grpcClient
	s.mu.RUnlock()

	if client == nil {
		w.WriteHeader(http.StatusServiceUnavailable)
		json.NewEncoder(w).Encode(map[string]string{"error": "runtime server not initialized"})
		return
	}

	path := r.URL.Path
	parts := splitPath(path)
	if len(parts) < 5 {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{"error": "task ID is required"})
		return
	}
	taskID := parts[3]

	var req struct {
		Reason string `json:"reason"`
	}
	_ = json.NewDecoder(r.Body).Decode(&req)

	resp, err := client.CancelTask(r.Context(), &runtime.CancelTaskRequest{
		TaskId: taskID,
		Reason: req.Reason,
	})
	if err != nil {
		if grpcStatus, ok := status.FromError(err); ok && grpcStatus.Code() == codes.NotFound {
			w.WriteHeader(http.StatusNotFound)
			json.NewEncoder(w).Encode(map[string]string{"error": "task not found"})
			return
		}
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": "failed to cancel task: " + err.Error()})
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"success": resp.Success,
	})
}

// HandleApproveTask handles POST /api/v1/tasks/{id}/approve
func (s *Supervisor) HandleApproveTask(w http.ResponseWriter, r *http.Request) {
	s.mu.RLock()
	client := s.grpcClient
	s.mu.RUnlock()

	if client == nil {
		w.WriteHeader(http.StatusServiceUnavailable)
		json.NewEncoder(w).Encode(map[string]string{"error": "runtime server not initialized"})
		return
	}

	path := r.URL.Path
	parts := splitPath(path)
	if len(parts) < 5 {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{"error": "task ID is required"})
		return
	}
	taskID := parts[3]

	var req struct {
		Reason string `json:"reason"`
	}
	_ = json.NewDecoder(r.Body).Decode(&req)

	resp, err := client.ApproveTask(r.Context(), &runtime.ApproveTaskRequest{
		TaskId: taskID,
		Reason: req.Reason,
	})
	if err != nil {
		if grpcStatus, ok := status.FromError(err); ok && grpcStatus.Code() == codes.NotFound {
			w.WriteHeader(http.StatusNotFound)
			json.NewEncoder(w).Encode(map[string]string{"error": "task not found"})
			return
		}
		if grpcStatus, ok := status.FromError(err); ok && grpcStatus.Code() == codes.FailedPrecondition {
			w.WriteHeader(http.StatusBadRequest)
			json.NewEncoder(w).Encode(map[string]string{"error": grpcStatus.Message()})
			return
		}
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": "failed to approve task: " + err.Error()})
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"success": resp.Success,
		"task":    protoTaskToFullJSON(resp.Task, nil),
	})
}

// HandleRejectTask handles POST /api/v1/tasks/{id}/reject
func (s *Supervisor) HandleRejectTask(w http.ResponseWriter, r *http.Request) {
	s.mu.RLock()
	client := s.grpcClient
	s.mu.RUnlock()

	if client == nil {
		w.WriteHeader(http.StatusServiceUnavailable)
		json.NewEncoder(w).Encode(map[string]string{"error": "runtime server not initialized"})
		return
	}

	path := r.URL.Path
	parts := splitPath(path)
	if len(parts) < 5 {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{"error": "task ID is required"})
		return
	}
	taskID := parts[3]

	var req struct {
		Reason string `json:"reason"`
	}
	_ = json.NewDecoder(r.Body).Decode(&req)

	resp, err := client.RejectTask(r.Context(), &runtime.RejectTaskRequest{
		TaskId: taskID,
		Reason: req.Reason,
	})
	if err != nil {
		if grpcStatus, ok := status.FromError(err); ok && grpcStatus.Code() == codes.NotFound {
			w.WriteHeader(http.StatusNotFound)
			json.NewEncoder(w).Encode(map[string]string{"error": "task not found"})
			return
		}
		if grpcStatus, ok := status.FromError(err); ok && grpcStatus.Code() == codes.FailedPrecondition {
			w.WriteHeader(http.StatusBadRequest)
			json.NewEncoder(w).Encode(map[string]string{"error": grpcStatus.Message()})
			return
		}
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": "failed to reject task: " + err.Error()})
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"success": resp.Success,
		"task":    protoTaskToFullJSON(resp.Task, nil),
	})
}

// protoTaskToFullJSON converts a protobuf Task to CLI/GUI-compatible JSON map (snake_case)
func protoTaskToFullJSON(task *runtime.Task, steps []*runtime.Step) map[string]interface{} {
	if task == nil {
		return nil
	}
	result := map[string]interface{}{
		"id":         task.Id,
		"query":      task.Query,
		"status":     mapTaskStatus(task.Status),
		"created_at": protoTimestampToISO(task.CreatedAt),
		"updated_at": protoTimestampToISO(task.UpdatedAt),
		"result":     task.Result,
		"error":      task.Error,
		"steps":      []map[string]interface{}{},
	}
	if task.CompletedAt != nil {
		result["completed_at"] = protoTimestampToISO(task.CompletedAt)
	}
	if steps != nil {
		stepJSON := make([]map[string]interface{}, 0, len(steps))
		for _, step := range steps {
			stepJSON = append(stepJSON, protoStepToFullJSON(step))
		}
		result["steps"] = stepJSON
	}
	return result
}

// protoStepToFullJSON converts a protobuf Step to CLI/GUI-compatible JSON map (snake_case)
func protoStepToFullJSON(step *runtime.Step) map[string]interface{} {
	if step == nil {
		return nil
	}
	description := step.ToolName
	if step.ToolInput != "" {
		description = step.ToolName + ": " + step.ToolInput
	}
	result := map[string]interface{}{
		"id":          fmt.Sprintf("step-%d", step.Index),
		"index":       step.Index,
		"description": description,
		"status":      mapStepStatus(step.Status),
		"result":      step.ToolOutput,
	}
	if step.StartedAt != nil {
		result["started_at"] = protoTimestampToISO(step.StartedAt)
	}
	if step.CompletedAt != nil {
		result["completed_at"] = protoTimestampToISO(step.CompletedAt)
	}
	return result
}

// protoTimestampToISO converts a protobuf Timestamp to ISO 8601 string
func protoTimestampToISO(ts *timestamppb.Timestamp) string {
	if ts == nil {
		return ""
	}
	return ts.AsTime().UTC().Format(time.RFC3339)
}

// mapTaskStatus maps protobuf TaskStatus to GUI-friendly string
func mapTaskStatus(status runtime.TaskStatus) string {
	switch status {
	case runtime.TaskStatus_TASK_STATUS_PENDING:
		return "pending"
	case runtime.TaskStatus_TASK_STATUS_PLANNING,
		runtime.TaskStatus_TASK_STATUS_EXECUTING,
		runtime.TaskStatus_TASK_STATUS_VERIFYING,
		runtime.TaskStatus_TASK_STATUS_AWAITING_APPROVAL:
		return "running"
	case runtime.TaskStatus_TASK_STATUS_COMPLETED:
		return "completed"
	case runtime.TaskStatus_TASK_STATUS_FAILED:
		return "failed"
	case runtime.TaskStatus_TASK_STATUS_CANCELLED:
		return "cancelled"
	default:
		return "pending"
	}
}

// mapStringToTaskType maps a string task type to protobuf TaskType
func mapStringToTaskType(typeStr string) runtime.TaskType {
	switch typeStr {
	case "simple":
		return runtime.TaskType_TASK_TYPE_SIMPLE
	case "complex":
		return runtime.TaskType_TASK_TYPE_COMPLEX
	case "desktop":
		return runtime.TaskType_TASK_TYPE_DESKTOP
	case "autonomous":
		return runtime.TaskType_TASK_TYPE_AUTONOMOUS
	default:
		return runtime.TaskType_TASK_TYPE_COMPLEX
	}
}

// mapStepStatus maps protobuf StepStatus to GUI-friendly string
func mapStepStatus(status runtime.StepStatus) string {
	switch status {
	case runtime.StepStatus_STEP_STATUS_PENDING:
		return "pending"
	case runtime.StepStatus_STEP_STATUS_EXECUTING:
		return "running"
	case runtime.StepStatus_STEP_STATUS_COMPLETED:
		return "completed"
	case runtime.StepStatus_STEP_STATUS_FAILED:
		return "failed"
	case runtime.StepStatus_STEP_STATUS_SKIPPED:
		return "skipped"
	default:
		return "pending"
	}
}

// ServeHTTP starts the HTTP server
func (s *Supervisor) ServeHTTP(config *Config) error {
	mux := http.NewServeMux()

	// Health and status endpoints
	mux.HandleFunc("/health", s.HandleHealth)
	mux.HandleFunc("/healthz", s.HandleHealth) // k8s style
	mux.HandleFunc("/status", s.HandleStatus)

	// Lifecycle management endpoints - Python
	mux.HandleFunc("/api/v1/python/start", s.HandleStartPython)
	mux.HandleFunc("/api/v1/python/stop", s.HandleStopPython)

	// Lifecycle management endpoints - gRPC
	mux.HandleFunc("/api/v1/grpc/start", s.HandleStartGRPC)
	mux.HandleFunc("/api/v1/grpc/stop", s.HandleStopGRPC)
	mux.HandleFunc("/api/v1/grpc/health", s.HandleGRPCHealth)

	// Task management endpoints
	mux.HandleFunc("/api/v1/tasks", s.HandleTasksRoute)
	mux.HandleFunc("/api/v1/tasks/", s.HandleTasksRoute)

	// Agent session endpoints
	mux.HandleFunc("/api/v1/agents", s.HandleListSessions)
	mux.HandleFunc("/api/v1/agents/", s.HandleAgentSession)

	// Desktop automation endpoints (for CLI)
	mux.HandleFunc("/api/v1/desktop/", s.HandleDesktopRoute)

	// Agent configuration endpoints (AgentBuilder)
	mux.HandleFunc("/api/v1/agent-configs", s.HandleAgentConfigRoute)
	mux.HandleFunc("/api/v1/agent-configs/", s.HandleAgentConfigRoute)

	// Tool definition endpoints (Tools page)
	mux.HandleFunc("/api/v1/tools", s.HandleToolRoute)
	mux.HandleFunc("/api/v1/tools/", s.HandleToolRoute)

	// Update endpoints
	mux.HandleFunc("/api/v1/update/check", s.HandleCheckUpdate)

	// WebSocket event bus endpoint
	if hub := s.eventHub; hub != nil {
		mux.HandleFunc("/api/v1/events", hub.HandleWebSocket)
	}

	addr := config.Host + ":" + config.PortStr()
	log.Printf("Supervisor HTTP server starting on %s", addr)
	log.Printf("Task endpoints: /api/v1/tasks, /api/v1/tasks/{id}, /api/v1/tasks/{id}/cancel")
	log.Printf("gRPC management endpoints: /api/v1/grpc/start, /api/v1/grpc/stop, /api/v1/grpc/health")

	s.httpServer = &http.Server{
		Addr:    addr,
		Handler: mux,
	}
	return s.httpServer.ListenAndServe()
}

// Shutdown gracefully shuts down all supervisor services
func (s *Supervisor) Shutdown(ctx context.Context) error {
	log.Println("Shutdown: starting graceful shutdown...")

	// 1. Stop accepting new HTTP requests
	if s.httpServer != nil {
		log.Println("Shutdown: stopping HTTP server...")
		if err := s.httpServer.Shutdown(ctx); err != nil {
			log.Printf("Shutdown: HTTP server shutdown error: %v", err)
		}
	}

	// 2. Cancel running tasks
	if s.runtimeServer != nil {
		log.Println("Shutdown: cancelling running tasks...")
		// TODO: Implement task cancellation in RuntimeServer
	}

	// 3. Stop MCP servers
	log.Println("Shutdown: stopping MCP servers...")
	if err := s.stopMCPServers(); err != nil {
		log.Printf("Shutdown: MCP server stop error: %v", err)
	}

	// 4. Stop Python executor
	log.Println("Shutdown: stopping Python executor...")
	if err := s.stopPythonExecutor(); err != nil {
		log.Printf("Shutdown: Python executor stop error: %v", err)
	}

	// 5. Stop Python runtime (SIGTERM first, then SIGKILL after timeout)
	log.Println("Shutdown: stopping Python runtime...")
	if err := s.stopPythonRuntimeGraceful(ctx); err != nil {
		log.Printf("Shutdown: Python runtime stop error: %v", err)
	}

	// 6. Stop gRPC servers
	log.Println("Shutdown: stopping gRPC servers...")
	if err := s.stopGRPCServer(); err != nil {
		log.Printf("Shutdown: gRPC server stop error: %v", err)
	}
	if err := s.stopCheckpointGRPCServer(); err != nil {
		log.Printf("Shutdown: checkpoint gRPC server stop error: %v", err)
	}

	// 6b. Close gRPC client connection
	if s.grpcConn != nil {
		log.Println("Shutdown: closing gRPC client connection...")
		if err := s.grpcConn.Close(); err != nil {
			log.Printf("Shutdown: gRPC client close error: %v", err)
		}
	}

	// 7. Close database
	if s.db != nil {
		log.Println("Shutdown: closing database...")
		if err := s.db.Close(); err != nil {
			log.Printf("Shutdown: database close error: %v", err)
		}
	}

	// 8. Close event hub
	if s.eventHub != nil {
		log.Println("Shutdown: closing event hub...")
		s.eventHub.Close()
	}

	log.Println("Shutdown: complete")
	return nil
}

// stopPythonRuntimeGraceful stops the Python runtime with SIGTERM, then SIGKILL after timeout
func (s *Supervisor) stopPythonRuntimeGraceful(ctx context.Context) error {
	if s.pythonCmd == nil || s.pythonCmd.Process == nil {
		return nil
	}

	// Try SIGTERM first
	log.Println("Shutdown: sending SIGTERM to Python runtime...")
	if err := s.pythonCmd.Process.Signal(os.Interrupt); err != nil {
		log.Printf("Shutdown: SIGTERM failed, using Kill: %v", err)
		return s.pythonCmd.Process.Kill()
	}

	// Wait for process to exit or timeout
	done := make(chan error, 1)
	go func() {
		done <- s.pythonCmd.Wait()
	}()

	select {
	case <-ctx.Done():
		log.Println("Shutdown: Python runtime SIGTERM timeout, sending SIGKILL...")
		return s.pythonCmd.Process.Kill()
	case err := <-done:
		if err != nil {
			log.Printf("Shutdown: Python runtime exited with error: %v", err)
		} else {
			log.Println("Shutdown: Python runtime exited cleanly")
		}
		return nil
	}
}

// HandleAgentSession routes agent session requests based on method
func (s *Supervisor) HandleAgentSession(w http.ResponseWriter, r *http.Request) {
	// Extract session ID from path
	path := r.URL.Path
	sessionID := ""

	// Parse session ID from /api/v1/agents/{id}
	parts := splitPath(path)
	if len(parts) >= 3 {
		sessionID = parts[2]
	}

	switch r.Method {
	case http.MethodPost:
		// Create new session (no ID in path)
		s.HandleCreateSession(w, r)
	case http.MethodGet:
		if sessionID != "" {
			// Get specific session
			s.HandleGetSession(w, r)
		} else {
			// List sessions
			s.HandleListSessions(w, r)
		}
	case http.MethodPut:
		if sessionID != "" {
			// Update session
			s.HandleUpdateSession(w, r)
		}
	case http.MethodDelete:
		if sessionID != "" {
			// Delete session
			s.HandleDeleteSession(w, r)
		}
	default:
		w.WriteHeader(http.StatusMethodNotAllowed)
		json.NewEncoder(w).Encode(map[string]string{"error": "method not allowed"})
	}
}

// extractPathParam extracts the parameter portion after a prefix in a URL path.
// e.g., extractPathParam("/api/v1/agents/abc-123", "/api/v1/agents/") returns "abc-123"
func extractPathParam(path, prefix string) string {
	if len(path) <= len(prefix) {
		return ""
	}
	result := path[len(prefix):]
	// Strip trailing slash
	if len(result) > 0 && result[len(result)-1] == '/' {
		result = result[:len(result)-1]
	}
	return result
}

// splitPath splits a path into segments
func splitPath(path string) []string {
	// Remove leading slash and split
	path = path[1:]
	return splitString(path, "/")
}

// splitString splits a string by delimiter
func splitString(s, sep string) []string {
	var result []string
	var current string
	for i := 0; i < len(s); i++ {
		if s[i] == sep[0] && (i+1 >= len(s) || s[i+1] != sep[0]) {
			if current != "" {
				result = append(result, current)
				current = ""
			}
		} else {
			current += string(s[i])
		}
	}
	if current != "" {
		result = append(result, current)
	}
	return result
}


// HandleCheckUpdate handles GET /api/v1/update/check
func (s *Supervisor) HandleCheckUpdate(w http.ResponseWriter, r *http.Request) {
s.mu.RLock()
	u := s.updater
s.mu.RUnlock()

	if u == nil {
		w.WriteHeader(http.StatusServiceUnavailable)
		json.NewEncoder(w).Encode(map[string]string{"error": "updater not initialized"})
		return
	}

	info, err := u.CheckUpdate()
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
		return
	}

	w.Header().Set("Content-Type", "application/json")
w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(info)
}

