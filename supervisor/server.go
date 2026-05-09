package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os/exec"
	"sync"
	"time"
)

// ServerState represents the current state of the supervisor
type ServerState struct {
	Running     bool        `json:"running"`
	StartTime   time.Time   `json:"start_time"`
	PythonReady bool        `json:"python_ready"`
	MCPServers  []MCPStatus `json:"mcp_servers"`
}

// MCPStatus represents the status of an MCP server
type MCPStatus struct {
	Name     string `json:"name"`
	Running  bool   `json:"running"`
	Port     int    `json:"port"`
	LastPing string   `json:"last_ping"`
}

// HealthResponse represents the health check response
type HealthResponse struct {
	Status     string    `json:"status"`
	Timestamp  time.Time `json:"timestamp"`
	Version    string    `json:"version"`
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
	mcpServers  map[string]*MCPStatus
	config      *Config
	db          *DB
	agentStore  *AgentSessionStore
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

// Start starts the supervisor and its services
func (s *Supervisor) Start() error {
	s.mu.Lock()
	defer s.mu.Unlock()

	// Start Python runtime
	if err := s.startPythonRuntime(); err != nil {
		log.Printf("Warning: Failed to start Python runtime: %v", err)
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

// GetHealth returns the current health status
func (s *Supervisor) GetHealth() HealthResponse {
	s.mu.RLock()
	defer s.mu.RUnlock()

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
			Name:   "python_runtime",
			Status: boolToStatus(s.state.PythonReady),
			Message: boolToMessage(s.state.PythonReady, "Python runtime not started"),
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
		Status:    "healthy",
		Timestamp: time.Now(),
		Version:   "0.1.0",
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
		"running":        s.state.Running,
		"start_time":     s.state.StartTime,
		"python_ready":   s.state.PythonReady,
		"python_port":    8000,
		"supervisor_port": s.config.Port,
		"mcp_servers":    s.mcpServers,
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

// ServeHTTP starts the HTTP server
func (s *Supervisor) ServeHTTP(config *Config) error {
	mux := http.NewServeMux()

	// Health and status endpoints
	mux.HandleFunc("/health", s.HandleHealth)
	mux.HandleFunc("/healthz", s.HandleHealth) // k8s style
	mux.HandleFunc("/status", s.HandleStatus)

	// Lifecycle management endpoints
	mux.HandleFunc("/api/v1/python/start", s.HandleStartPython)
	mux.HandleFunc("/api/v1/python/stop", s.HandleStopPython)

	// Agent session endpoints
	mux.HandleFunc("/api/v1/agents", s.HandleListSessions)
	mux.HandleFunc("/api/v1/agents/", s.HandleAgentSession)

	addr := config.Host + ":" + config.PortStr()
	log.Printf("Supervisor HTTP server starting on %s", addr)

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
