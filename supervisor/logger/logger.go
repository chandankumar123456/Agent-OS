package logger

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"time"
)

// LogLevel represents the logging level
type LogLevel int

const (
	DebugLevel LogLevel = iota
	InfoLevel
	WarnLevel
	ErrorLevel
)

// String returns the string representation of the log level
func (l LogLevel) String() string {
	return [...]string{"DEBUG", "INFO", "WARN", "ERROR"}[l]
}

// Logger represents the structured logger
type Logger struct {
	level      LogLevel
	logger     *log.Logger
	jsonOutput bool
}

// New creates a new logger instance
func New(logLevel string, jsonOutput bool) (*Logger, error) {
	level, err := parseLogLevel(logLevel)
	if err != nil {
		return nil, err
	}

	return &Logger{
		level:      level,
		logger:     log.New(os.Stdout, "", 0),
		jsonOutput: jsonOutput,
	}, nil
}

// parseLogLevel converts a string log level to LogLevel
func parseLogLevel(level string) (LogLevel, error) {
	switch level {
	case "debug":
		return DebugLevel, nil
	case "info":
		return InfoLevel, nil
	case "warn":
		return WarnLevel, nil
	case "error":
		return ErrorLevel, nil
	default:
		return InfoLevel, fmt.Errorf("invalid log level: %s", level)
	}
}

// LogEntry represents a structured log entry
type LogEntry struct {
	Timestamp string         `json:"timestamp"`
	Level     string         `json:"level"`
	Message   string         `json:"message"`
	Fields    map[string]any `json:"fields,omitempty"`
}

// Log logs a message with the given level and fields
func (l *Logger) Log(level LogLevel, message string, fields map[string]any) {
	if level < l.level {
		return
	}

	entry := LogEntry{
		Timestamp: time.Now().Format(time.RFC3339),
		Level:     level.String(),
		Message:   message,
		Fields:    fields,
	}

	if l.jsonOutput {
		l.logJSON(entry)
	} else {
		l.logText(entry)
	}
}

// logJSON outputs the log entry as JSON
func (l *Logger) logJSON(entry LogEntry) {
	data, err := json.Marshal(entry)
	if err != nil {
		l.logger.Printf("[ERROR] Failed to marshal log entry: %v", err)
		return
	}
	l.logger.Println(string(data))
}

// logText outputs the log entry as plain text
func (l *Logger) logText(entry LogEntry) {
	fieldsStr := ""
	if len(entry.Fields) > 0 {
		var pairs []string
		for k, v := range entry.Fields {
			pairs = append(pairs, fmt.Sprintf("%s=%v", k, v))
		}
		fieldsStr = fmt.Sprintf(" | %s", joinStrings(pairs, ", "))
	}
	l.logger.Printf("[%s] %s%s", entry.Level, entry.Message, fieldsStr)
}

// joinStrings joins a slice of strings with a separator
func joinStrings(strs []string, sep string) string {
	if len(strs) == 0 {
		return ""
	}
	if len(strs) == 1 {
		return strs[0]
	}
	result := strs[0]
	for i := 1; i < len(strs); i++ {
		result += sep + strs[i]
	}
	return result
}

// Debug logs a debug message
func (l *Logger) Debug(message string, fields ...map[string]any) {
	l.Log(DebugLevel, message, getFields(fields))
}

// Info logs an info message
func (l *Logger) Info(message string, fields ...map[string]any) {
	l.Log(InfoLevel, message, getFields(fields))
}

// Warn logs a warning message
func (l *Logger) Warn(message string, fields ...map[string]any) {
	l.Log(WarnLevel, message, getFields(fields))
}

// Error logs an error message
func (l *Logger) Error(message string, fields ...map[string]any) {
	l.Log(ErrorLevel, message, getFields(fields))
}

// getFields extracts fields from variadic parameter
func getFields(fields []map[string]any) map[string]any {
	if len(fields) == 0 {
		return nil
	}
	return fields[0]
}

// Debugf logs a formatted debug message
func (l *Logger) Debugf(format string, args ...any) {
	l.Log(DebugLevel, fmt.Sprintf(format, args...), nil)
}

// Infof logs a formatted info message
func (l *Logger) Infof(format string, args ...any) {
	l.Log(InfoLevel, fmt.Sprintf(format, args...), nil)
}

// Warnf logs a formatted warning message
func (l *Logger) Warnf(format string, args ...any) {
	l.Log(WarnLevel, fmt.Sprintf(format, args...), nil)
}

// Errorf logs a formatted error message
func (l *Logger) Errorf(format string, args ...any) {
	l.Log(ErrorLevel, fmt.Sprintf(format, args...), nil)
}

// Fatalf logs a formatted error message and exits
func (l *Logger) Fatalf(format string, args ...any) {
	l.Log(ErrorLevel, fmt.Sprintf(format, args...), nil)
	os.Exit(1)
}
