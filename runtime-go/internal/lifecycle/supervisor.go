package lifecycle

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"time"

	"github.com/AgentOS/agentos-runtime/internal/crypto"
	"github.com/AgentOS/agentos-runtime/internal/update"
)

// Config holds application configuration from flags and environment
type Config struct {
	Host                  string
	Port                  int
	LogLevel              string
	DataDir               string
	Version               bool
	Help                  bool
	PythonExecutorEnabled bool
	PythonExecutorAddress string
	PythonExecutorTimeout int
	Update                update.Config
}

// PortStr returns the port as a string
func (c *Config) PortStr() string {
	return fmt.Sprintf("%d", c.Port)
}

// Validate checks configuration for validity
func (c *Config) Validate() error {
	validLevels := map[string]bool{
		"debug": true,
		"info":  true,
		"warn":  true,
		"error": true,
	}
	if !validLevels[c.LogLevel] {
		return fmt.Errorf("invalid log level: %s (must be debug, info, warn, or error)", c.LogLevel)
	}

	if c.Port < 1 || c.Port > 65535 {
		return fmt.Errorf("invalid port: %d (must be 1-65535)", c.Port)
	}

	return nil
}

// State represents the current state of the supervisor
type State struct {
	Running     bool      `json:"running"`
	StartTime   time.Time `json:"start_time"`
	PythonReady bool      `json:"python_ready"`
	KernelReady bool      `json:"kernel_ready"`
	KernelPort  int       `json:"kernel_port"`
}

// Supervisor holds the supervisor state and manages the Python kernel process
type Supervisor struct {
	mu            sync.RWMutex
	state         State
	pythonCmd     *exec.Cmd
	config        *Config
	cryptoManager *crypto.CryptoManager
	apiKey        string
	updater       *update.Updater
	eventHub      *EventHub
	kernelClient  *KernelClient
}

// NewSupervisor creates a new supervisor instance
func NewSupervisor(config *Config) *Supervisor {
	return &Supervisor{
		state: State{
			Running:   true,
			StartTime: time.Now(),
		},
		config: config,
	}
}

// SetCryptoManager sets the crypto manager
func (s *Supervisor) SetCryptoManager(cm *crypto.CryptoManager) {
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

// SetUpdater sets the updater
func (s *Supervisor) SetUpdater(updater *update.Updater) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.updater = updater
}

// SetEventHub sets the event hub
func (s *Supervisor) SetEventHub(hub *EventHub) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.eventHub = hub
}

func (s *Supervisor) projectRoot() string {
	wd, err := os.Getwd()
	if err != nil {
		return ""
	}
	if _, err := os.Stat(filepath.Join(wd, "core")); err == nil {
		return wd
	}
	parent := filepath.Dir(wd)
	if _, err := os.Stat(filepath.Join(parent, "core")); err == nil {
		return parent
	}
	return ""
}

// Start starts the supervisor and its services
func (s *Supervisor) Start() error {
	s.mu.Lock()

	// Start Python kernel process
	if err := s.startPythonKernel(); err != nil {
		log.Printf("Warning: Failed to start Python kernel: %v", err)
	}

	s.mu.Unlock()

	// Connect gRPC client to Python kernel (retries take time, do outside lock)
	if err := s.connectKernelClient(); err != nil {
		log.Printf("Warning: Failed to connect kernel client: %v", err)
	}

	return nil
}

// startPythonKernel starts the Python core kernel process
func (s *Supervisor) startPythonKernel() error {
	pythonPath, err := exec.LookPath("python")
	if err != nil {
		return err
	}

	cmd := exec.Command(pythonPath, "-m", "core")
	cmd.Env = append(os.Environ(),
		"AGENTOS_RUNTIME_MODE=grpc",
		fmt.Sprintf("AGENTOS_API_KEY=%s", s.apiKey),
		fmt.Sprintf("AGENTOS_CERT_DIR=%s", filepath.Join(s.config.DataDir, "certs")),
	)
	if root := s.projectRoot(); root != "" {
		cmd.Dir = root
	}

	if err := cmd.Start(); err != nil {
		return err
	}

	s.pythonCmd = cmd
	s.state.PythonReady = true

	if s.eventHub != nil {
		s.eventHub.EmitProcessEvent(EventProcessStarted, "python-kernel", "started", "")
	}

	log.Printf("Python kernel started (PID %d)", cmd.Process.Pid)
	return nil
}

// connectKernelClient establishes a gRPC client connection to the Python kernel
func (s *Supervisor) connectKernelClient() error {
	client := NewKernelClient("localhost:50051")

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	if err := client.Connect(ctx, 10); err != nil {
		return err
	}

	s.mu.Lock()
	s.kernelClient = client
	s.state.KernelReady = true
	s.state.KernelPort = 50051
	s.mu.Unlock()

	return nil
}

// StopPythonKernel stops the Python kernel process
func (s *Supervisor) StopPythonKernel() error {
	if s.pythonCmd != nil && s.pythonCmd.Process != nil {
		return s.pythonCmd.Process.Kill()
	}
	return nil
}

// IsKernelHealthy checks if the kernel client connection is healthy
func (s *Supervisor) IsKernelHealthy() bool {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.state.KernelReady && s.kernelClient != nil && s.kernelClient.IsConnected()
}

// Shutdown gracefully shuts down all supervisor services
func (s *Supervisor) Shutdown(ctx context.Context) error {
	log.Println("Shutdown: starting graceful shutdown...")

	// Stop Python kernel (SIGTERM first, then SIGKILL after timeout)
	log.Println("Shutdown: stopping Python kernel...")
	if err := s.stopPythonKernelGraceful(ctx); err != nil {
		log.Printf("Shutdown: Python kernel stop error: %v", err)
	}

	// Close kernel client connection
	if s.kernelClient != nil {
		log.Println("Shutdown: closing kernel client connection...")
		if err := s.kernelClient.Close(); err != nil {
			log.Printf("Shutdown: kernel client close error: %v", err)
		}
	}

	// Close event hub
	if s.eventHub != nil {
		log.Println("Shutdown: closing event hub...")
		s.eventHub.Close()
	}

	log.Println("Shutdown: complete")
	return nil
}

// stopPythonKernelGraceful stops the Python kernel with SIGTERM, then SIGKILL
func (s *Supervisor) stopPythonKernelGraceful(ctx context.Context) error {
	if s.pythonCmd == nil || s.pythonCmd.Process == nil {
		return nil
	}

	// Try SIGTERM first
	log.Println("Shutdown: sending SIGTERM to Python kernel...")
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
		log.Println("Shutdown: Python kernel SIGTERM timeout, sending SIGKILL...")
		return s.pythonCmd.Process.Kill()
	case err := <-done:
		if err != nil {
			log.Printf("Shutdown: Python kernel exited with error: %v", err)
		} else {
			log.Println("Shutdown: Python kernel exited cleanly")
		}
		return nil
	}
}

// GetState returns a copy of the current supervisor state
func (s *Supervisor) GetState() State {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.state
}
