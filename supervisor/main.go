package main

import (
	"context"
	"database/sql"
	"flag"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/AgentOS/supervisor/logger"

	_ "modernc.org/sqlite"
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
	Update                UpdateConfig
}

// UpdateConfig holds auto-update configuration
type UpdateConfig struct {
	Enabled  bool
	URL      string
	Channel  string // "stable", "beta", "dev"
	Interval string // e.g., "24h"
}

// PortStr returns the port as a string
func (c *Config) PortStr() string {
	return fmt.Sprintf("%d", c.Port)
}

// ParseConfig reads command-line flags and returns a Config struct
func ParseConfig() *Config {
	config := &Config{}

	// Define flags
	host := flag.String("host", "127.0.0.1", "Host to bind to")
	port := flag.Int("port", 8080, "Port to listen on")
	logLevel := flag.String("log-level", "info", "Logging level (debug, info, warn, error)")
	dataDir := flag.String("data-dir", "", "Directory for data storage (defaults to user config dir)")
	version := flag.Bool("version", false, "Print version and exit")
	help := flag.Bool("help", false, "Show help and exit")

	flag.Parse()

	// Set parsed values
	config.Host = *host
	config.Port = *port
	config.LogLevel = *logLevel
	config.Version = *version
	config.Help = *help

	// Set default update config
	config.Update = UpdateConfig{
		Enabled:  true,
		URL:      "https://releases.agentos.dev",
		Channel:  "stable",
		Interval: "24h",
	}

	// Determine data directory
	if *dataDir == "" {
		// Use platform-appropriate config directory
		homeDir, err := os.UserHomeDir()
		if err != nil {
			// Fallback to current directory
			homeDir = "."
		}
		config.DataDir = filepath.Join(homeDir, ".agentos")
	} else {
		config.DataDir = *dataDir
	}

	return config
}

// ShowHelp prints usage information
func ShowHelp() {
	helpText := `AgentOS Supervisor - Local-native runtime supervisor

Usage: supervisor [options]

Options:
  -host string
    	Host to bind to (default "127.0.0.1")
  -port int
    	Port to listen on (default 8080)
  -log-level string
    	Logging level: debug, info, warn, error (default "info")
  -data-dir string
    	Directory for data storage (default: ~/.agentos)
  -version
    	Print version and exit
  -help
    	Show this help message

Examples:
  supervisor                    # Run with default settings
  supervisor -port 9000         # Run on port 9000
  supervisor -log-level debug   # Enable debug logging
  supervisor -data-dir /custom/path  # Use custom data directory

Version: 0.1.0 (Phase 1 - Foundation)
`
	fmt.Print(helpText)
}

// PrintVersion prints version information
func PrintVersion() {
	fmt.Println("AgentOS Supervisor v0.1.0 (Phase 1 - Foundation)")
	fmt.Println("Local-native runtime supervisor for AgentOS")
}

// ValidateConfig checks configuration for validity
func (c *Config) Validate() error {
	// Validate log level
	validLevels := map[string]bool{
		"debug": true,
		"info":  true,
		"warn":  true,
		"error": true,
	}
	if !validLevels[c.LogLevel] {
		return fmt.Errorf("invalid log level: %s (must be debug, info, warn, or error)", c.LogLevel)
	}

	// Validate port range
	if c.Port < 1 || c.Port > 65535 {
		return fmt.Errorf("invalid port: %d (must be 1-65535)", c.Port)
	}

	return nil
}

// DB holds the database connection and configuration
type DB struct {
	path   string
	conn   *sql.DB
	logger *logger.Logger
}

// New creates a new database connection
func New(dataDir string, logger *logger.Logger) (*DB, error) {
	// Ensure data directory exists
	if err := os.MkdirAll(dataDir, 0755); err != nil {
		return nil, fmt.Errorf("failed to create data directory: %w", err)
	}

	// Build database path
	dbPath := filepath.Join(dataDir, "agentos.db")

	// Open database connection (modernc.org/sqlite auto-registers as "sqlite")
	conn, err := sql.Open("sqlite", dbPath)
	if err != nil {
		return nil, fmt.Errorf("failed to open database: %w", err)
	}

	// Test connection
	if err := conn.Ping(); err != nil {
		return nil, fmt.Errorf("failed to ping database: %w", err)
	}

	return &DB{
		path:   dbPath,
		conn:   conn,
		logger: logger,
	}, nil
}

// Close closes the database connection
func (db *DB) Close() error {
	if db.conn != nil {
		return db.conn.Close()
	}
	return nil
}

// Path returns the database file path
func (db *DB) Path() string {
	return db.path
}

// GetSystemState retrieves a value from the system_state table
func (db *DB) GetSystemState(key string) (string, error) {
	var value string
	err := db.conn.QueryRow(`SELECT value FROM system_state WHERE key = ?`, key).Scan(&value)
	if err == sql.ErrNoRows {
		return "", nil
	}
	if err != nil {
		return "", err
	}
	return value, nil
}

// SetSystemState stores a value in the system_state table
func (db *DB) SetSystemState(key, value string) error {
	_, err := db.conn.Exec(
		`INSERT INTO system_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP`,
		key, value,
	)
	return err
}

// Migrate runs database migrations
func (db *DB) Migrate() error {
	// Create tables if they don't exist
	queries := []string{
		// Agent sessions table
		`
		CREATE TABLE IF NOT EXISTS agent_sessions (
			id TEXT PRIMARY KEY,
			agent_id TEXT NOT NULL,
			status TEXT NOT NULL DEFAULT 'pending',
			input TEXT,
			output TEXT,
			error_message TEXT,
			started_at DATETIME,
			completed_at DATETIME,
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
		)
		`,

		// Actions table
		`
		CREATE TABLE IF NOT EXISTS actions (
			id TEXT PRIMARY KEY,
			session_id TEXT NOT NULL,
			sequence INTEGER NOT NULL,
			action_type TEXT NOT NULL,
			target TEXT,
			arguments TEXT,
			status TEXT NOT NULL DEFAULT 'pending',
			result TEXT,
			error_message TEXT,
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			foreign key (session_id) references agent_sessions(id)
		)
		`,

		// System state table
		`
		CREATE TABLE IF NOT EXISTS system_state (
			key TEXT PRIMARY KEY,
			value TEXT NOT NULL,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
		)
		`,

		// Agent configurations table (for AgentBuilder page)
		`
		CREATE TABLE IF NOT EXISTS agent_configs (
			id TEXT PRIMARY KEY,
			name TEXT NOT NULL,
			description TEXT NOT NULL DEFAULT '',
			role TEXT NOT NULL DEFAULT 'assistant',
			system_prompt TEXT,
			model TEXT,
			temperature REAL DEFAULT 0.7,
			max_tokens INTEGER DEFAULT 2048,
			tools TEXT DEFAULT '[]',
			status TEXT NOT NULL DEFAULT 'active',
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
		)
		`,

		// Tool definitions table (for Tools page)
		`
		CREATE TABLE IF NOT EXISTS tool_definitions (
			id TEXT PRIMARY KEY,
			name TEXT NOT NULL UNIQUE,
			description TEXT NOT NULL DEFAULT '',
			category TEXT NOT NULL DEFAULT 'general',
			type TEXT NOT NULL DEFAULT 'builtin',
			status TEXT NOT NULL DEFAULT 'available',
			parameters_schema TEXT DEFAULT '{}',
			tags TEXT DEFAULT '[]',
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
		)
		`,

		// Checkpoints table for LangGraph state persistence
		`
		CREATE TABLE IF NOT EXISTS checkpoints (
			id TEXT PRIMARY KEY,
			thread_id TEXT NOT NULL,
			checkpoint_ns INTEGER NOT NULL,
			checkpoint_type TEXT NOT NULL,
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			state_blob BLOB,
			channel_values BLOB,
			pending_sends BLOB,
			parent_ids TEXT,
			metadata TEXT,
			task_id TEXT,
			foreign key (thread_id) references agent_sessions(id)
		)
		`,

		// Indexes for performance
		`
		CREATE INDEX IF NOT EXISTS idx_agent_sessions_agent_id ON agent_sessions(agent_id)
		`,
		`
		CREATE INDEX IF NOT EXISTS idx_agent_sessions_status ON agent_sessions(status)
		`,
		`
		CREATE INDEX IF NOT EXISTS idx_agent_sessions_started_at ON agent_sessions(started_at)
		`,
		`
		CREATE INDEX IF NOT EXISTS idx_actions_session_id ON actions(session_id)
		`,
		`
		CREATE INDEX IF NOT EXISTS idx_actions_status ON actions(status)
		`,
		`
		CREATE INDEX IF NOT EXISTS idx_checkpoints_thread_id ON checkpoints(thread_id)
		`,
		`
		CREATE INDEX IF NOT EXISTS idx_checkpoints_checkpoint_ns ON checkpoints(checkpoint_ns)
		`,
	}

	for _, query := range queries {
		_, err := db.conn.Exec(query)
		if err != nil {
			return fmt.Errorf("failed to execute migration: %w", err)
		}
	}

	// Seed default agent configs if table is empty
	var agentCount int
	err := db.conn.QueryRow(`SELECT COUNT(*) FROM agent_configs`).Scan(&agentCount)
	if err == nil && agentCount == 0 {
		defaultAgents := []string{
			`INSERT INTO agent_configs (id, name, description, role, status) VALUES ('web-researcher', 'Web Researcher', 'Searches the web for information and summarizes findings', 'researcher', 'active')`,
			`INSERT INTO agent_configs (id, name, description, role, tools, status) VALUES ('file-organizer', 'File Organizer', 'Organizes files based on content analysis and naming patterns', 'organizer', '["read_file","write_file","execute_command"]', 'active')`,
			`INSERT INTO agent_configs (id, name, description, role, tools, status) VALUES ('desktop-automator', 'Desktop Automator', 'Performs desktop automation tasks like clicks and typing', 'automator', '["screenshot","click_element","type_text"]', 'active')`,
			`INSERT INTO agent_configs (id, name, description, role, tools, status) VALUES ('code-assistant', 'Code Assistant', 'Writes and reviews code with best practices', 'developer', '["read_file","write_file","execute_command","execute_python"]', 'active')`,
			`INSERT INTO agent_configs (id, name, description, role, tools, status) VALUES ('document-analyst', 'Document Analyst', 'Parses and analyzes PDF, DOCX, and other documents', 'analyst', '["read_file","parse_document","search_web"]', 'active')`,
		}
		for _, q := range defaultAgents {
			db.conn.Exec(q)
		}
	}

	// Seed default tool definitions if table is empty
	var toolCount int
	err = db.conn.QueryRow(`SELECT COUNT(*) FROM tool_definitions`).Scan(&toolCount)
	if err == nil && toolCount == 0 {
		defaultTools := []string{
			`INSERT INTO tool_definitions (id, name, description, category, type) VALUES ('read-file', 'Read File', 'Read contents of a file from the filesystem', 'Filesystem', 'builtin')`,
			`INSERT INTO tool_definitions (id, name, description, category, type) VALUES ('write-file', 'Write File', 'Write content to a file on the filesystem', 'Filesystem', 'builtin')`,
			`INSERT INTO tool_definitions (id, name, description, category, type) VALUES ('execute-command', 'Execute Command', 'Run shell commands on the host system', 'Shell', 'builtin')`,
			`INSERT INTO tool_definitions (id, name, description, category, type) VALUES ('search-web', 'Search Web', 'Search the web using DuckDuckGo search engine', 'Cloud API', 'builtin')`,
			`INSERT INTO tool_definitions (id, name, description, category, type) VALUES ('navigate-browser', 'Navigate Browser', 'Navigate to a URL in the browser environment', 'Browser', 'builtin')`,
			`INSERT INTO tool_definitions (id, name, description, category, type) VALUES ('take-screenshot', 'Screenshot', 'Take a screenshot of the current desktop', 'Desktop', 'builtin')`,
			`INSERT INTO tool_definitions (id, name, description, category, type) VALUES ('click-element', 'Click Element', 'Click at specific screen coordinates', 'Desktop', 'builtin')`,
			`INSERT INTO tool_definitions (id, name, description, category, type) VALUES ('type-text', 'Type Text', 'Type text at the current cursor position', 'Desktop', 'builtin')`,
			`INSERT INTO tool_definitions (id, name, description, category, type) VALUES ('parse-document', 'Parse Document', 'Parse PDF, DOCX, and TXT files for content extraction', 'Document', 'builtin')`,
			`INSERT INTO tool_definitions (id, name, description, category, type) VALUES ('execute-python', 'Execute Python', 'Execute Python code in a sandboxed environment', 'Code', 'builtin')`,
			`INSERT INTO tool_definitions (id, name, description, category, type) VALUES ('list-windows', 'List Windows', 'Enumerate all visible windows on the desktop', 'Desktop', 'builtin')`,
			`INSERT INTO tool_definitions (id, name, description, category, type) VALUES ('focus-window', 'Focus Window', 'Bring a window to focus by title', 'Desktop', 'builtin')`,
		}
		for _, q := range defaultTools {
			db.conn.Exec(q)
		}
	}

	return nil
}

// testDatabaseOperations performs basic database operations to verify functionality
func testDatabaseOperations(dbConn *DB) error {
	fmt.Println("Testing database operations...")

	// Test inserting a system state
	_, err := dbConn.conn.Exec(
		`INSERT INTO system_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = ?`,
		"supervisor_version", "0.1.0", "0.1.0",
	)
	if err != nil {
		return fmt.Errorf("failed to insert system state: %w", err)
	}

	// Test reading system state
	var value string
	err = dbConn.conn.QueryRow(`SELECT value FROM system_state WHERE key = ?`, "supervisor_version").Scan(&value)
	if err != nil {
		return fmt.Errorf("failed to query system state: %w", err)
	}

	if value != "0.1.0" {
		return fmt.Errorf("unexpected value: expected '0.1.0', got '%s'", value)
	}

	fmt.Println("Database operations test passed!")
	return nil
}

func main() {
	// Parse configuration
	config := ParseConfig()

	// Handle special flags
	if config.Version {
		PrintVersion()
		os.Exit(0)
	}

	if config.Help {
		ShowHelp()
		os.Exit(0)
	}

	// Validate configuration
	if err := config.Validate(); err != nil {
		fmt.Fprintf(os.Stderr, "Configuration error: %v\n", err)
		os.Exit(1)
	}

	// Initialize structured logger
	logger, err := logger.New(config.LogLevel, false) // false = text output, true = JSON
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to initialize logger: %v\n", err)
		os.Exit(1)
	}

	// Initialize database with logger
	dbConn, err := New(config.DataDir, logger)
	if err != nil {
		logger.Errorf("Failed to initialize database: %v", err)
		os.Exit(1)
	}
	defer dbConn.Close()

	// Run migrations
	if err := dbConn.Migrate(); err != nil {
		logger.Errorf("Failed to run migrations: %v", err)
		os.Exit(1)
	}

	logger.Info("Database initialized successfully")

	// Verify database was created
	if _, err := os.Stat(dbConn.Path()); os.IsNotExist(err) {
		logger.Fatalf("Database file was not created at: %s", dbConn.Path())
	}
	logger.Infof("Database file verified at: %s", dbConn.Path())

	// Test database operations
	if err := testDatabaseOperations(dbConn); err != nil {
		logger.Errorf("Database operations test failed: %v", err)
		os.Exit(1)
	}

	// Initialize crypto manager and ensure TLS certs exist
	cryptoMgr := NewCryptoManager(config.DataDir)
	if err := cryptoMgr.EnsureCertsExist(); err != nil {
		logger.Errorf("Failed to initialize TLS certificates: %v", err)
		os.Exit(1)
	}
	logger.Info("TLS certificates initialized")

	// Ensure API key exists
	apiKey, err := dbConn.GetSystemState("api_key")
	if err != nil || apiKey == "" {
		apiKey, err = GenerateAPIKey()
		if err != nil {
			logger.Errorf("Failed to generate API key: %v", err)
			os.Exit(1)
		}
		if err := dbConn.SetSystemState("api_key", apiKey); err != nil {
			logger.Errorf("Failed to store API key: %v", err)
			os.Exit(1)
		}
		logger.Info("Generated new API key for local auth")
	} else {
		logger.Info("Loaded existing API key")
	}

	// Create supervisor instance
	supervisor := NewSupervisor(config)
	supervisor.SetDB(dbConn)
	supervisor.SetCryptoManager(cryptoMgr)
	supervisor.SetAPIKey(apiKey)

	// Initialize runtime server
	runtimeServer := NewRuntimeServer(dbConn, logger)
	supervisor.SetRuntimeServer(runtimeServer)

	// Initialize checkpoint server with TLS + auth
	checkpointServer := NewCheckpointServer(dbConn, logger)
	checkpointServer.SetAuthKey(apiKey)
	supervisor.SetCheckpointServer(checkpointServer)

	// Initialize updater
	updater := NewUpdater(config)
	supervisor.SetUpdater(updater)

	// Initialize event hub for WebSocket events
	eventHub := NewEventHub()
	supervisor.SetEventHub(eventHub)

	// Wire runtime server events to event hub
	runtimeServer.SetEventHandler(func(eventType string, taskID string, status string, query string, errMsg string) {
		if errMsg != "" {
			eventHub.EmitTaskError(taskID, status, errMsg)
		} else {
			eventHub.EmitTaskEvent(eventType, taskID, status, query)
		}
	})

	// Initialize agent session store
	if err := supervisor.InitializeAgentStore(); err != nil {
		fmt.Fprintf(os.Stderr, "Failed to initialize agent store: %v\n", err)
		os.Exit(1)
	}

	// Start supervisor services
	if err := supervisor.Start(); err != nil {
		fmt.Fprintf(os.Stderr, "Warning: Failed to start supervisor services: %v\n", err)
	}

	// Set up signal handling
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	fmt.Println("AgentOS Supervisor started successfully")
	fmt.Printf("HTTP API available at http://%s:%s\n", config.Host, config.PortStr())
	fmt.Printf("Press Ctrl+C to shutdown\n")

	// Start HTTP server in goroutine
	go func() {
		if err := supervisor.ServeHTTP(config); err != nil && err != http.ErrServerClosed {
			fmt.Fprintf(os.Stderr, "HTTP server failed: %v\n", err)
			os.Exit(1)
		}
	}()

	// Wait for shutdown signal
	<-sigChan
	fmt.Println("\nShutdown signal received, cleaning up...")

	// Graceful shutdown with 30-second timeout
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	if err := supervisor.Shutdown(shutdownCtx); err != nil {
		fmt.Fprintf(os.Stderr, "Warning: Shutdown error: %v\n", err)
	}

	fmt.Println("Shutdown complete")
}
