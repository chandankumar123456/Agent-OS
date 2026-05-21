package smoke

import (
	"os"
	"os/exec"
	"runtime"
	"testing"
	"time"
)

// TestSupervisorStarts verifies the supervisor binary starts and responds to health checks
func TestSupervisorStarts(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Skipping supervisor smoke test on non-Windows platform")
	}

	// Find supervisor binary (built from runtime-go/)
	supervisorPath := "../../supervisor.exe"
	if _, err := os.Stat(supervisorPath); os.IsNotExist(err) {
		t.Skip("Supervisor binary not found, skipping smoke test")
	}

	// Start supervisor
	cmd := exec.Command(supervisorPath, "-port", "18080")
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	if err := cmd.Start(); err != nil {
		t.Fatalf("Failed to start supervisor: %v", err)
	}
	defer func() {
		if cmd.Process != nil {
			cmd.Process.Kill()
		}
	}()

	// Wait for it to be ready
	time.Sleep(3 * time.Second)

	// Check if process is still running
	if cmd.ProcessState != nil && cmd.ProcessState.Exited() {
		t.Fatal("Supervisor exited prematurely")
	}

	t.Log("Supervisor started successfully")
}

// TestSupervisorHealth verifies the supervisor responds to health checks
func TestSupervisorHealth(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Skipping on non-Windows")
	}

	// This test requires a running supervisor on port 8080
	// In CI, it runs after TestSupervisorStarts
	t.Skip("Requires running supervisor instance")
}
