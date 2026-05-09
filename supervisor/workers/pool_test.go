package workers

import (
	"fmt"
	"testing"
	"time"
)

func TestNewPool(t *testing.T) {
	config := &PoolConfig{
		MinWorkers:  2,
		MaxWorkers:  10,
		QueueSize:   100,
		TaskTimeout: 5 * time.Second,
	}
	
	pool := NewPool(config)
	
	if pool.minWorkers != 2 {
		t.Errorf("expected minWorkers=2, got %d", pool.minWorkers)
	}
	if pool.maxWorkers != 10 {
		t.Errorf("expected maxWorkers=10, got %d", pool.maxWorkers)
	}
	if pool.queueSize != 100 {
		t.Errorf("expected queueSize=100, got %d", pool.queueSize)
	}
}

func TestDefaultConfig(t *testing.T) {
	config := DefaultConfig()
	
	if config.MinWorkers != 2 {
		t.Errorf("expected MinWorkers=2, got %d", config.MinWorkers)
	}
	if config.MaxWorkers != 100 {
		t.Errorf("expected MaxWorkers=100, got %d", config.MaxWorkers)
	}
	if config.QueueSize != 1000 {
		t.Errorf("expected QueueSize=1000, got %d", config.QueueSize)
	}
}

func TestPoolStartStop(t *testing.T) {
	config := &PoolConfig{
		MinWorkers:  2,
		MaxWorkers:  5,
		QueueSize:   10,
		TaskTimeout: 1 * time.Second,
	}
	
	pool := NewPool(config)
	
	// Test Start
	err := pool.Start()
	if err != nil {
		t.Fatalf("failed to start pool: %v", err)
	}
	
	// Verify running state
	if !pool.running {
		t.Error("expected pool to be running")
	}
	
	// Verify workers created
	if pool.workerCount != config.MinWorkers {
		t.Errorf("expected %d workers, got %d", config.MinWorkers, pool.workerCount)
	}
	
	// Test Stop
	err = pool.Stop()
	if err != nil {
		t.Fatalf("failed to stop pool: %v", err)
	}
	
	// Verify stopped state
	if pool.running {
		t.Error("expected pool to be stopped")
	}
}

func TestSubmitTask(t *testing.T) {
	config := &PoolConfig{
		MinWorkers:  1,
		MaxWorkers:  3,
		QueueSize:   10,
		TaskTimeout: 1 * time.Second,
	}
	
	pool := NewPool(config)
	err := pool.Start()
	if err != nil {
		t.Fatalf("failed to start pool: %v", err)
	}
	defer pool.Stop()
	
	// Submit a task
	task := &Task{
		ID:       "test-task-1",
		Type:     "test",
		Payload:  map[string]interface{}{"key": "value"},
		Priority: 1,
	}
	
	err = pool.Submit(task)
	if err != nil {
		t.Fatalf("failed to submit task: %v", err)
	}
	
	// Check metrics
	metrics := pool.GetMetrics()
	if metrics["tasks_submitted"] != int64(1) {
		t.Errorf("expected 1 submitted task, got %d", metrics["tasks_submitted"])
	}
}

func TestSubmitNilTask(t *testing.T) {
	pool := NewPool(DefaultConfig())
	err := pool.Start()
	if err != nil {
		t.Fatalf("failed to start pool: %v", err)
	}
	defer pool.Stop()
	
	err = pool.Submit(nil)
	if err == nil {
		t.Error("expected error for nil task")
	}
}

func TestSubmitTaskWithoutID(t *testing.T) {
	pool := NewPool(DefaultConfig())
	err := pool.Start()
	if err != nil {
		t.Fatalf("failed to start pool: %v", err)
	}
	defer pool.Stop()
	
	task := &Task{
		Type:    "test",
		Payload: map[string]interface{}{},
	}
	
	err = pool.Submit(task)
	if err == nil {
		t.Error("expected error for task without ID")
	}
}

func TestPoolNotRunning(t *testing.T) {
	pool := NewPool(DefaultConfig())
	
	task := &Task{
		ID:   "test",
		Type: "test",
	}
	
	err := pool.Submit(task)
	if err == nil {
		t.Error("expected error when pool not running")
	}
}

func BenchmarkTaskSubmission(b *testing.B) {
	config := &PoolConfig{
		MinWorkers:  2,
		MaxWorkers:  10,
		QueueSize:   b.N + 100,
		TaskTimeout: 1 * time.Second,
	}
	
	pool := NewPool(config)
	err := pool.Start()
	if err != nil {
		b.Fatalf("failed to start pool: %v", err)
	}
	defer pool.Stop()
	
	b.ResetTimer()
	
	for i := 0; i < b.N; i++ {
		task := &Task{
			ID:       fmt.Sprintf("task-%d", i),
			Type:     "benchmark",
			Payload:  map[string]interface{}{"index": i},
			Priority: 1,
		}
		pool.Submit(task)
	}
}

func TestScaleWorkers(t *testing.T) {
	config := &PoolConfig{
		MinWorkers:  2,
		MaxWorkers:  10,
		QueueSize:   10,
		TaskTimeout: 1 * time.Second,
	}
	
	pool := NewPool(config)
	err := pool.Start()
	if err != nil {
		t.Fatalf("failed to start pool: %v", err)
	}
	defer pool.Stop()
	
	// Scale up
	err = pool.ScaleWorkers(5)
	if err != nil {
		t.Fatalf("failed to scale workers: %v", err)
	}
	
	// Give time for workers to spawn
	time.Sleep(100 * time.Millisecond)
	
	if pool.workerCount < 5 {
		t.Errorf("expected at least 5 workers, got %d", pool.workerCount)
	}
	
	// Test invalid scale (below min)
	err = pool.ScaleWorkers(1)
	if err == nil {
		t.Error("expected error when scaling below min")
	}
	
	// Test invalid scale (above max)
	err = pool.ScaleWorkers(20)
	if err == nil {
		t.Error("expected error when scaling above max")
	}
}

func TestGetMetrics(t *testing.T) {
	pool := NewPool(DefaultConfig())
	
	metrics := pool.GetMetrics()
	
	expectedKeys := []string{"workers_active", "workers_min", "workers_max", 
		"tasks_submitted", "tasks_completed", "tasks_failed", "queue_length", "running"}
	
	for _, key := range expectedKeys {
		if _, ok := metrics[key]; !ok {
			t.Errorf("expected metric key '%s' not found", key)
		}
	}
}
