package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
)

// Config holds application configuration from flags and environment
type Config struct {
	Host        string
	Port        int
	LogLevel    string
	DataDir     string
	Version     bool
	Help        bool
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

func main() {
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
		ShowHelp()
		os.Exit(1)
	}

	// TODO: Initialize and start supervisor
	fmt.Printf("Starting AgentOS Supervisor...\n")
	fmt.Printf("  Host: %s\n", config.Host)
	fmt.Printf("  Port: %d\n", config.Port)
	fmt.Printf("  Log Level: %s\n", config.LogLevel)
	fmt.Printf("  Data Directory: %s\n", config.DataDir)

	// Placeholder for supervisor initialization
	fmt.Println("Supervisor initialized. Waiting for shutdown signal...")
}
