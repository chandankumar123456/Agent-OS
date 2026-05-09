// Package workers provides a high-performance worker pool for task execution
// using Go goroutines for true parallelism, replacing Python asyncio workers.
package workers

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"sync"
	"time"

	"github.com/AgentOS/supervisor/workers/grpcclient"
	pb "github.com/AgentOS/supervisor/proto"
)

// Task represents a unit of work to be executed by a worker
type Task struct {
	ID         string                 `json:"id"`
	Type       string                 `json:"type"`
	Payload    map[string]interface{} `json:"payload"`
	Priority   int                    `json:"priority"`
	CreatedAt  time.Time              `json:"created_at"`
	Timeout    time.Duration          `json:"timeout"`
	Retries    int                    `json:"retries"`
	MaxRetries int                    `json:"max_retries"`
}

// TaskResult represents the outcome of task execution
type TaskResult struct {
	TaskID      string                 `json:"task_id"`
	Success     bool                   `json:"success"`
	Output      map[string]interface{} `json:"output"`
	Error       string                 `json:"error,omitempty"`
	Duration    time.Duration          `json:"duration"`
	WorkerID    string                 `json:"worker_id"`
	CompletedAt time.Time              `json:"completed_at"`
}

// Worker represents a single worker goroutine
type Worker struct {
	id       string
	pool     *Pool
	taskChan chan *Task
	quitChan chan struct{}
	active   bool
	mu       sync.RWMutex
}

// Pool manages a dynamic pool of workers
type Pool struct {
	// Configuration
	minWorkers  int
	maxWorkers  int
	queueSize   int
	taskTimeout time.Duration

	// Channels
	taskQueue  chan *Task
	resultChan chan *TaskResult

	// Workers
	workers     map[string]*Worker
	workerCount int
	mu          sync.RWMutex

	// Task tracking
	taskMap map[string]*Task
	taskMu  sync.RWMutex

	// Control
	ctx     context.Context
	cancel  context.CancelFunc
	wg      sync.WaitGroup
	running bool

	// Metrics
	tasksSubmitted int64
	tasksCompleted int64
	tasksFailed    int64
	metricsMu      sync.RWMutex

	// gRPC client for Python executor
	grpcClient *grpcclient.Client
}

// PoolConfig contains configuration for the worker pool
type PoolConfig struct {
	MinWorkers  int           `json:"min_workers"`
	MaxWorkers  int           `json:"max_workers"`
	QueueSize   int           `json:"queue_size"`
	TaskTimeout time.Duration `json:"task_timeout"`
}

// DefaultConfig returns a default pool configuration
func DefaultConfig() *PoolConfig {
	return &PoolConfig{
		MinWorkers:  2,
		MaxWorkers:  100,
		QueueSize:   1000,
		TaskTimeout: 30 * time.Second,
	}
}

// NewPool creates a new worker pool with the given configuration
func NewPool(config *PoolConfig) *Pool {
	if config == nil {
		config = DefaultConfig()
	}

	ctx, cancel := context.WithCancel(context.Background())

	pool := &Pool{
		minWorkers:  config.MinWorkers,
		maxWorkers:  config.MaxWorkers,
		queueSize:   config.QueueSize,
		taskTimeout: config.TaskTimeout,
		taskQueue:   make(chan *Task, config.QueueSize),
		resultChan:  make(chan *TaskResult, config.QueueSize),
		workers:     make(map[string]*Worker),
		taskMap:     make(map[string]*Task),
		ctx:         ctx,
		cancel:      cancel,
	}

	// Initialize gRPC client for Python executor
	// Connect to localhost:50052 (Python executor service)
	grpcClient, err := grpcclient.NewClient("localhost:50052")
	if err != nil {
		log.Printf("[WARN] Failed to connect to Python executor gRPC server: %v", err)
		log.Printf("[WARN] Worker pool will continue without gRPC client - tasks will use fallback execution")
	} else {
		pool.grpcClient = grpcClient
		log.Printf("[INFO] Connected to Python executor gRPC server at localhost:50052")
	}

	return pool
}

// Start initializes the worker pool and starts the minimum number of workers
func (p *Pool) Start() error {
	p.mu.Lock()
	defer p.mu.Unlock()

	if p.running {
		return fmt.Errorf("pool already running")
	}

	p.running = true

	// Start minimum workers
	for i := 0; i < p.minWorkers; i++ {
		p.spawnWorker()
	}

	// Start task dispatcher
	p.wg.Add(1)
	go p.dispatcher()

	// Start metrics collector
	p.wg.Add(1)
	go p.metricsCollector()

	log.Printf("[INFO] Worker pool started: min_workers=%d max_workers=%d queue_size=%d",
		p.minWorkers, p.maxWorkers, p.queueSize)

	return nil
}

// Stop gracefully shuts down the worker pool
func (p *Pool) Stop() error {
	p.mu.Lock()
	if !p.running {
		p.mu.Unlock()
		return fmt.Errorf("pool not running")
	}
	p.running = false
	p.mu.Unlock()

	// Cancel context to signal workers
	p.cancel()

	// Signal all workers to quit
	p.mu.RLock()
	for _, worker := range p.workers {
		worker.Stop()
	}
	p.mu.RUnlock()

	// Wait for all goroutines to finish
	done := make(chan struct{})
	go func() {
		p.wg.Wait()
		close(done)
	}()

	select {
	case <-done:
		log.Println("[INFO] Worker pool stopped gracefully")
	case <-time.After(30 * time.Second):
		log.Println("[WARN] Worker pool stop timeout - forcing shutdown")
	}

	// Close gRPC client connection
	if p.grpcClient != nil {
		if err := p.grpcClient.Close(); err != nil {
			log.Printf("[WARN] Error closing gRPC client: %v", err)
		} else {
			log.Println("[INFO] gRPC client connection closed")
		}
	}

	return nil
}

// Submit adds a task to the queue for execution
func (p *Pool) Submit(task *Task) error {
	if task == nil {
		return fmt.Errorf("task cannot be nil")
	}

	if task.ID == "" {
		return fmt.Errorf("task ID cannot be empty")
	}

	p.mu.RLock()
	if !p.running {
		p.mu.RUnlock()
		return fmt.Errorf("pool not running")
	}
	p.mu.RUnlock()

	// Set defaults
	if task.CreatedAt.IsZero() {
		task.CreatedAt = time.Now()
	}
	if task.Timeout == 0 {
		task.Timeout = p.taskTimeout
	}
	if task.MaxRetries == 0 {
		task.MaxRetries = 3
	}

	// Store task
	p.taskMu.Lock()
	p.taskMap[task.ID] = task
	p.taskMu.Unlock()

	// Submit to queue
	select {
	case p.taskQueue <- task:
		p.metricsMu.Lock()
		p.tasksSubmitted++
		p.metricsMu.Unlock()
		log.Printf("[DEBUG] Task submitted: task_id=%s type=%s", task.ID, task.Type)
		return nil
	case <-time.After(5 * time.Second):
		return fmt.Errorf("task queue full - submission timeout")
	}
}

// GetResult returns the result channel
func (p *Pool) GetResult() <-chan *TaskResult {
	return p.resultChan
}

// GetMetrics returns current pool metrics
func (p *Pool) GetMetrics() map[string]interface{} {
	p.metricsMu.RLock()
	p.mu.RLock()
	defer p.metricsMu.RUnlock()
	defer p.mu.RUnlock()

	return map[string]interface{}{
		"workers_active":  p.workerCount,
		"workers_min":     p.minWorkers,
		"workers_max":     p.maxWorkers,
		"tasks_submitted": p.tasksSubmitted,
		"tasks_completed": p.tasksCompleted,
		"tasks_failed":    p.tasksFailed,
		"queue_length":    len(p.taskQueue),
		"running":         p.running,
	}
}

// spawnWorker creates and starts a new worker
func (p *Pool) spawnWorker() {
	p.mu.Lock()
	defer p.mu.Unlock()

	if p.workerCount >= p.maxWorkers {
		return
	}

	workerID := fmt.Sprintf("worker-%d", p.workerCount+1)
	worker := &Worker{
		id:       workerID,
		pool:     p,
		taskChan: make(chan *Task, 1),
		quitChan: make(chan struct{}),
		active:   true,
	}

	p.workers[workerID] = worker
	p.workerCount++

	p.wg.Add(1)
	go worker.run()

	log.Printf("[DEBUG] Worker spawned: worker_id=%s total_workers=%d", workerID, p.workerCount)
}

// dispatcher routes tasks to available workers
func (p *Pool) dispatcher() {
	defer p.wg.Done()

	for {
		select {
		case <-p.ctx.Done():
			return

		case task := <-p.taskQueue:
			// Find available worker
			p.mu.RLock()
			for _, worker := range p.workers {
				if worker.active {
					select {
					case worker.taskChan <- task:
						p.mu.RUnlock()
						goto dispatched
					default:
						// Worker busy, try next
					}
				}
			}
			p.mu.RUnlock()

			// No available worker, spawn new if under max
			p.mu.RLock()
			if p.workerCount < p.maxWorkers {
				p.mu.RUnlock()
				p.spawnWorker()
				// Retry dispatch
				go func() {
					p.taskQueue <- task
				}()
			} else {
				p.mu.RUnlock()
				// Queue full, return to queue
				go func() {
					select {
					case p.taskQueue <- task:
					case <-time.After(100 * time.Millisecond):
						// If still can't queue, this is a problem
						log.Printf("[ERROR] Task dispatch failed - queue full: task_id=%s", task.ID)
					}
				}()
			}
		dispatched:
		}
	}
}

// run is the main worker loop
func (w *Worker) run() {
	defer w.pool.wg.Done()

	log.Printf("[INFO] Worker started: worker_id=%s", w.id)

	for {
		select {
		case <-w.quitChan:
			log.Printf("[INFO] Worker stopped: worker_id=%s", w.id)
			return

		case task := <-w.taskChan:
			w.executeTask(task)
		}
	}
}

// executeTask executes a single task
func (w *Worker) executeTask(task *Task) {
	startTime := time.Now()

	log.Printf("[DEBUG] Task execution started: worker_id=%s task_id=%s type=%s",
		w.id, task.ID, task.Type)

	result := &TaskResult{
		TaskID:      task.ID,
		WorkerID:    w.id,
		CompletedAt: time.Now(),
	}

	// Create timeout context
	ctx, cancel := context.WithTimeout(w.pool.ctx, task.Timeout)
	defer cancel()

	// Execute task (placeholder - will be replaced with actual task execution)
	done := make(chan struct{})
	go func() {
		defer close(done)

		// TODO: Implement actual task execution via Python bridge
		// For now, simulate task execution
		success, output, err := w.executeViaPython(task)

		result.Success = success
		result.Output = output
		if err != nil {
			result.Error = err.Error()
		}
	}()

	select {
	case <-done:
		// Task completed
		result.Duration = time.Since(startTime)

		// Update metrics
		w.pool.metricsMu.Lock()
		if result.Success {
			w.pool.tasksCompleted++
		} else {
			w.pool.tasksFailed++
		}
		w.pool.metricsMu.Unlock()

		// Send result
		select {
		case w.pool.resultChan <- result:
		case <-time.After(5 * time.Second):
			log.Printf("[ERROR] Result channel full - dropping result: task_id=%s", task.ID)
		}

		log.Printf("[DEBUG] Task execution completed: worker_id=%s task_id=%s duration=%v success=%v",
			w.id, task.ID, result.Duration, result.Success)

	case <-ctx.Done():
		// Task timeout
		result.Duration = time.Since(startTime)
		result.Success = false
		result.Error = fmt.Sprintf("task timeout after %v", task.Timeout)

		w.pool.metricsMu.Lock()
		w.pool.tasksFailed++
		w.pool.metricsMu.Unlock()

		select {
		case w.pool.resultChan <- result:
		case <-time.After(5 * time.Second):
			log.Printf("[ERROR] Result channel full - dropping result: task_id=%s", task.ID)
		}

		log.Printf("[WARN] Task execution timeout: worker_id=%s task_id=%s timeout=%v",
			w.id, task.ID, task.Timeout)
	}
}

// executeViaPython sends task to Python executor via gRPC
func (w *Worker) executeViaPython(task *Task) (bool, map[string]interface{}, error) {
	// Check if gRPC client is available
	if w.pool.grpcClient == nil {
		return false, nil, fmt.Errorf("gRPC client not available - Python executor not connected")
	}

	// Marshal task payload to JSON
	payload, err := json.Marshal(task.Payload)
	if err != nil {
		return false, nil, fmt.Errorf("failed to marshal task payload: %w", err)
	}

	// Create gRPC request
	req := &pb.ExecuteTaskRequest{
		TaskId:    task.ID,
		TaskType:  task.Type,
		Payload:   payload,
		Priority:  int32(task.Priority),
		TimeoutMs: int32(task.Timeout.Milliseconds()),
		Metadata: map[string]string{
			"worker_id":  w.id,
			"created_at": task.CreatedAt.Format(time.RFC3339),
		},
	}

	// Execute task via gRPC
	ctx, cancel := context.WithTimeout(w.pool.ctx, task.Timeout)
	defer cancel()

	resp, err := w.pool.grpcClient.ExecuteTask(ctx, req)
	if err != nil {
		return false, nil, fmt.Errorf("gRPC execution failed: %w", err)
	}

	// Parse result
	var output map[string]interface{}
	if len(resp.Result) > 0 {
		if err := json.Unmarshal(resp.Result, &output); err != nil {
			// If we can't unmarshal, return the raw result as a string
			output = map[string]interface{}{
				"raw_result": string(resp.Result),
			}
		}
	}

	// Add execution metadata
	output["execution_time_ms"] = resp.ExecutionTimeMs
	output["worker_id"] = resp.WorkerId

	return resp.Success, output, nil
}

// mustMarshalJSON marshals v to JSON, panicking on error
// Use only for data that is guaranteed to be serializable
func mustMarshalJSON(v interface{}) []byte {
	data, err := json.Marshal(v)
	if err != nil {
		panic(fmt.Sprintf("failed to marshal JSON: %v", err))
	}
	return data
}

// Stop signals the worker to stop
func (w *Worker) Stop() {
	w.mu.Lock()
	defer w.mu.Unlock()

	if w.active {
		w.active = false
		close(w.quitChan)
	}
}

// ScaleWorkers adjusts the number of workers in the pool
func (p *Pool) ScaleWorkers(targetCount int) error {
	p.mu.Lock()
	defer p.mu.Unlock()

	if targetCount < p.minWorkers || targetCount > p.maxWorkers {
		return fmt.Errorf("target count %d out of range [%d, %d]",
			targetCount, p.minWorkers, p.maxWorkers)
	}

	currentCount := p.workerCount

	if targetCount > currentCount {
		// Scale up
		for i := currentCount; i < targetCount; i++ {
			p.spawnWorker()
		}
		log.Printf("[INFO] Pool scaled up: from=%d to=%d", currentCount, targetCount)
	} else if targetCount < currentCount {
		// Scale down - mark excess workers for removal
		// They will stop after completing current tasks
		// TODO: Implement graceful scale-down
		log.Printf("[INFO] Pool scale down requested: from=%d to=%d", currentCount, targetCount)
	}

	return nil
}

// metricsCollector periodically logs pool metrics
func (p *Pool) metricsCollector() {
	defer p.wg.Done()

	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-p.ctx.Done():
			return
		case <-ticker.C:
			metrics := p.GetMetrics()
			log.Printf("[INFO] Pool metrics: workers=%d submitted=%d completed=%d failed=%d queue=%d",
				metrics["workers_active"],
				metrics["tasks_submitted"],
				metrics["tasks_completed"],
				metrics["tasks_failed"],
				metrics["queue_length"])
		}
	}
}
