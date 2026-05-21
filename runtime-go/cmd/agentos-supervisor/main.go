package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/AgentOS/agentos-runtime/internal/crypto"
	"github.com/AgentOS/agentos-runtime/internal/lifecycle"
	"github.com/AgentOS/agentos-runtime/internal/logger"
	"github.com/AgentOS/agentos-runtime/internal/update"
)

// ParseConfig reads command-line flags and returns a Config struct
func ParseConfig() *lifecycle.Config {
	config := &lifecycle.Config{}

	host := flag.String("host", "127.0.0.1", "Host to bind to")
	port := flag.Int("port", 8080, "Port to listen on")
	logLevel := flag.String("log-level", "info", "Logging level (debug, info, warn, error)")
	dataDir := flag.String("data-dir", "", "Directory for data storage (defaults to user config dir)")
	version := flag.Bool("version", false, "Print version and exit")
	help := flag.Bool("help", false, "Show help and exit")

	flag.Parse()

	config.Host = *host
	config.Port = *port
	config.LogLevel = *logLevel
	config.Version = *version
	config.Help = *help

	// Set default update config
	config.Update = update.Config{
		Enabled:  true,
		URL:      "https://releases.agentos.dev",
		Channel:  "stable",
		Interval: "24h",
	}

	// Determine data directory
	if *dataDir == "" {
		homeDir, err := os.UserHomeDir()
		if err != nil {
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

Usage: agentos-supervisor [options]

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
  agentos-supervisor                    # Run with default settings
  agentos-supervisor -port 9000         # Run on port 9000
  agentos-supervisor -log-level debug   # Enable debug logging
  agentos-supervisor -data-dir /custom/path  # Use custom data directory

Version: 0.4.0 (Phase 5 - Lifecycle/Update/Crypto only)
`
	fmt.Print(helpText)
}

// PrintVersion prints version information
func PrintVersion() {
	fmt.Println("AgentOS Supervisor v0.4.0")
	fmt.Println("Local-native lifecycle supervisor for AgentOS")
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
	log, err := logger.New(config.LogLevel, false)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to initialize logger: %v\n", err)
		os.Exit(1)
	}

	// Ensure data directory exists
	if err := os.MkdirAll(config.DataDir, 0755); err != nil {
		log.Errorf("Failed to create data directory: %v", err)
		os.Exit(1)
	}

	// Initialize crypto manager and ensure TLS certs exist
	cryptoMgr := crypto.NewCryptoManager(config.DataDir)
	if err := cryptoMgr.EnsureCertsExist(); err != nil {
		log.Errorf("Failed to initialize TLS certificates: %v", err)
		os.Exit(1)
	}
	log.Info("TLS certificates initialized")

	// Generate API key
	apiKey, err := crypto.GenerateAPIKey()
	if err != nil {
		log.Errorf("Failed to generate API key: %v", err)
		os.Exit(1)
	}
	log.Info("Generated API key for local auth")

	// Initialize updater
	updater := update.NewUpdater(config.Update)

	// Initialize event hub for lifecycle events
	eventHub := lifecycle.NewEventHub()

	// Create supervisor instance
	supervisor := lifecycle.NewSupervisor(config)
	supervisor.SetCryptoManager(cryptoMgr)
	supervisor.SetAPIKey(apiKey)
	supervisor.SetUpdater(updater)
	supervisor.SetEventHub(eventHub)

	// Start supervisor services
	if err := supervisor.Start(); err != nil {
		fmt.Fprintf(os.Stderr, "Warning: Failed to start supervisor services: %v\n", err)
	}

	// Set up signal handling
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	fmt.Println("AgentOS Supervisor started successfully")
	fmt.Printf("Lifecycle supervisor ready, managing Python kernel\n")
	fmt.Printf("Press Ctrl+C to shutdown\n")

	// Check for updates on startup
	if updater.ShouldAutoCheck() {
		go func() {
			info, err := updater.CheckUpdate()
			if err != nil {
				log.Debugf("Update check failed: %v", err)
				return
			}
			if info.Available {
				log.Infof("Update available: %s -> %s", info.CurrentVersion, info.LatestVersion)
			}
		}()
	}

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
