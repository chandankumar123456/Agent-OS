package main

import (
	"database/sql"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"

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

	// Create supervisor instance
	supervisor := NewSupervisor(config)
	supervisor.SetDB(dbConn)

	// Initialize checkpoint server
	checkpointServer := NewCheckpointServer(dbConn, logger)
	supervisor.SetCheckpointServer(checkpointServer)

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
		if err := supervisor.ServeHTTP(config); err != nil {
			fmt.Fprintf(os.Stderr, "HTTP server failed: %v\n", err)
			os.Exit(1)
		}
	}()

	// Wait for shutdown signal
	<-sigChan
	fmt.Println("\nShutdown signal received, cleaning up...")

	// Stop supervisor services
	if err := supervisor.stopPythonRuntime(); err != nil {
		fmt.Fprintf(os.Stderr, "Warning: Failed to stop Python runtime: %v\n", err)
	}
	if err := supervisor.stopPythonExecutor(); err != nil {
		fmt.Fprintf(os.Stderr, "Warning: Failed to stop Python executor: %v\n", err)
	}
	if err := supervisor.stopMCPServers(); err != nil {
		fmt.Fprintf(os.Stderr, "Warning: Failed to stop MCP servers: %v\n", err)
	}

	fmt.Println("Shutdown complete")
}
