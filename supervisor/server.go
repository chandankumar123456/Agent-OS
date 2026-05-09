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
	"sync"
	"time"

	"github.com/AgentOS/supervisor/proto"
	"github.com/AgentOS/supervisor/workers/grpcclient"
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
	mu          sync.RWMutex
	state       ServerState
	pythonCmd   *exec.Cmd
	grpcCmd     *exec.Cmd
	executorCmd *exec.Cmd // Python executor process
	mcpServers  map[string]*MCPStatus
	config      *Config
	db          *DB
	agentStore  *AgentSessionStore
	grpcClient  GRPCClient // gRPC client for worker pool management
}

// GRPCClient interface for gRPC operations (allows mocking)
type GRPCClient interface {
	// Using only the available proto types
	ExecuteTask(ctx context.Context, req *proto.TaskRequest) (*proto.TaskResponse, error)
	HealthCheck(ctx context.Context) error
	GetMetrics() grpcclient.Metrics
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

// SetGRPCClient sets the gRPC client for worker pool management
func (s *Supervisor) SetGRPCClient(client GRPCClient) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.grpcClient = client
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
	defer s.mu.Unlock()

	// Start Python runtime
	if err := s.startPythonRuntime(); err != nil {
		log.Printf("Warning: Failed to start Python runtime: %v", err)
	}

	// Start gRPC server
	if err := s.startGRPCServer(); err != nil {
		log.Printf("Warning: Failed to start gRPC server: %v", err)
	}

	// Start Python executor
	if err := s.startPythonExecutor(); err != nil {
		log.Printf("Warning: Failed to start Python executor: %v", err)
	}

	// Start MCP servers
	if err := s.startMCPServers(); err != nil {
		log.Printf("Warning: Failed to start MCP servers: %v", err)
	}

	return nil
}

// startPythonRuntime starts the Python FastAPI backend
func (s *Supervisor) startPythonRuntime() error {
	// Check if Python is available
	pythonPath, err := exec.LookPath("python")
	if err != nil {
		return err
	}

	// Use port 8000 for Python FastAPI backend (separate from supervisor port 8080)
	pythonPort := "8000"
	cmd := exec.Command(pythonPath, "-m", "uvicorn", "app.main:app",
		"--host", s.config.Host,
		"--port", pythonPort,
		"--reload",
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

	log.Printf("Python runtime started on %s:%s", s.config.Host, pythonPort)
	return nil
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
	cmd.Env = append(os.Environ(), "GRPC_PORT=50051")
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

// isGRPCHealthy checks if the gRPC server is responsive
func (s *Supervisor) isGRPCHealthy() bool {
	if !s.state.GRPCReady || s.grpcCmd == nil || s.grpcCmd.Process == nil {
		return false
	}
	if s.grpcCmd.ProcessState != nil && s.grpcCmd.ProcessState.Exited() {
		return false
	}
	return true
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

// HandleWorkerPoolStatus handles GET /api/v1/workers/status
func (s *Supervisor) HandleWorkerPoolStatus(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.WriteHeader(http.StatusMethodNotAllowed)
		json.NewEncoder(w).Encode(map[string]string{"error": "method not allowed"})
		return
	}

	s.mu.RLock()
	client := s.grpcClient
	s.mu.RUnlock()

	if client == nil {
		w.WriteHeader(http.StatusServiceUnavailable)
		json.NewEncoder(w).Encode(map[string]string{"error": "gRPC client not initialized"})
		return
	}

	// Stub response - proto types not yet available
	response := map[string]interface{}{
		"active_workers": 0,
		"queued_tasks":   0,
		"utilization":    0.0,
		"timestamp":      time.Now().Unix(),
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(response)
}

// HandleWorkerPoolScale handles POST /api/v1/workers/scale
func (s *Supervisor) HandleWorkerPoolScale(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.WriteHeader(http.StatusMethodNotAllowed)
		json.NewEncoder(w).Encode(map[string]string{"error": "method not allowed"})
		return
	}

	s.mu.RLock()
	client := s.grpcClient
	s.mu.RUnlock()

	if client == nil {
		w.WriteHeader(http.StatusServiceUnavailable)
		json.NewEncoder(w).Encode(map[string]string{"error": "gRPC client not initialized"})
		return
	}

	// Parse request body
	var req struct {
		WorkerCount int32 `json:"worker_count"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{"error": "invalid request body: " + err.Error()})
		return
	}

	if req.WorkerCount <= 0 {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{"error": "worker_count must be positive"})
		return
	}

	// Stub response - proto types not yet available
	response := map[string]interface{}{
		"worker_count": req.WorkerCount,
		"success":      true,
		"message":      "Worker pool scaling request accepted (stub)",
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(response)
}

// HandleWorkerHealth handles GET /api/v1/workers/{id}/health
func (s *Supervisor) HandleWorkerHealth(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.WriteHeader(http.StatusMethodNotAllowed)
		json.NewEncoder(w).Encode(map[string]string{"error": "method not allowed"})
		return
	}

	s.mu.RLock()
	client := s.grpcClient
	s.mu.RUnlock()

	if client == nil {
		w.WriteHeader(http.StatusServiceUnavailable)
		json.NewEncoder(w).Encode(map[string]string{"error": "gRPC client not initialized"})
		return
	}

	// Extract worker ID from URL path /api/v1/workers/{id}/health
	path := r.URL.Path
	parts := splitPath(path)
	var workerID string
	if len(parts) >= 4 {
		workerID = parts[2]
	}

	if workerID == "" {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{"error": "worker ID is required"})
		return
	}

	// Stub response - proto types not yet available
	response := map[string]interface{}{
		"worker_id":     workerID,
		"healthy":       true,
		"last_heartbeat": time.Now().Unix(),
		"message":       "Worker health check (stub)",
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(response)
}

// HandleWorkerMetrics handles GET /api/v1/workers/metrics
func (s *Supervisor) HandleWorkerMetrics(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.WriteHeader(http.StatusMethodNotAllowed)
		json.NewEncoder(w).Encode(map[string]string{"error": "method not allowed"})
		return
	}

	s.mu.RLock()
	client := s.grpcClient
	s.mu.RUnlock()

	if client == nil {
		w.WriteHeader(http.StatusServiceUnavailable)
		json.NewEncoder(w).Encode(map[string]string{"error": "gRPC client not initialized"})
		return
	}

	// Get local client metrics (not a gRPC call - returns accumulated metrics)
	metrics := client.GetMetrics()

	// Calculate average latency and success rate
	var avgLatency float64
	var successRate float64
	if metrics.TotalRequests > 0 {
		avgLatency = float64(metrics.TotalLatency.Milliseconds()) / float64(metrics.TotalRequests)
		successRate = float64(metrics.SuccessfulRequests) / float64(metrics.TotalRequests) * 100
	}

	response := map[string]interface{}{
		"total_requests":       metrics.TotalRequests,
		"successful_requests":  metrics.SuccessfulRequests,
		"failed_requests":      metrics.FailedRequests,
		"average_latency_ms":   avgLatency,
		"success_rate_percent": successRate,
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(response)
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

	// Worker pool management endpoints
	mux.HandleFunc("/api/v1/workers/status", s.HandleWorkerPoolStatus)
	mux.HandleFunc("/api/v1/workers/scale", s.HandleWorkerPoolScale)
	mux.HandleFunc("/api/v1/workers/metrics", s.HandleWorkerMetrics)
	mux.HandleFunc("/api/v1/workers/", s.HandleWorkerHealth) // Handles /api/v1/workers/{id}/health

	// Lifecycle management endpoints - gRPC
	mux.HandleFunc("/api/v1/grpc/start", s.HandleStartGRPC)
	mux.HandleFunc("/api/v1/grpc/stop", s.HandleStopGRPC)
	mux.HandleFunc("/api/v1/grpc/health", s.HandleGRPCHealth)

	// Agent session endpoints
	mux.HandleFunc("/api/v1/agents", s.HandleListSessions)
	mux.HandleFunc("/api/v1/agents/", s.HandleAgentSession)

	// Worker pool management endpoints
	mux.HandleFunc("/api/v1/workers/status", s.HandleWorkerPoolStatus)
	mux.HandleFunc("/api/v1/workers/scale", s.HandleWorkerPoolScale)
	mux.HandleFunc("/api/v1/workers/metrics", s.HandleWorkerMetrics)
	mux.HandleFunc("/api/v1/workers/", s.HandleWorkerHealth)

	addr := config.Host + ":" + config.PortStr()
	log.Printf("Supervisor HTTP server starting on %s", addr)
	log.Printf("gRPC management endpoints: /api/v1/grpc/start, /api/v1/grpc/stop, /api/v1/grpc/health")
	log.Printf("Worker pool endpoints: /api/v1/workers/status, /api/v1/workers/scale, /api/v1/workers/metrics, /api/v1/workers/{id}/health")

	return http.ListenAndServe(addr, mux)
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
