package worker

import (
	"context"
	"fmt"
	"sync"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/connectivity"
	"google.golang.org/grpc/credentials/insecure"

	"github.com/AgentOS/supervisor/logger"
	"github.com/AgentOS/supervisor/proto"
)

// PoolConfig defines configuration for the worker pool client
type PoolConfig struct {
	// Address is the gRPC server address (e.g., "localhost:50051")
	Address string
	// MaxConnections is the maximum number of concurrent connections
	MaxConnections int
	// ConnectionTimeout is the timeout for establishing a connection
	ConnectionTimeout time.Duration
	// KeepAliveInterval is the interval for sending keepalive pings
	KeepAliveInterval time.Duration
	// RetryPolicy defines the retry configuration
	RetryPolicy RetryPolicy
}

// RetryPolicy defines retry configuration
type RetryPolicy struct {
	MaxRetries  int
	InitialBackoff time.Duration
	MaxBackoff     time.Duration
	BackoffMultiplier float64
}

// DefaultPoolConfig returns a default configuration
func DefaultPoolConfig() PoolConfig {
	return PoolConfig{
		Address:           "localhost:50051",
		MaxConnections:    10,
		ConnectionTimeout:   5 * time.Second,
		KeepAliveInterval:   30 * time.Second,
		RetryPolicy: RetryPolicy{
			MaxRetries:        3,
			InitialBackoff:    100 * time.Millisecond,
			MaxBackoff:        5 * time.Second,
			BackoffMultiplier: 2.0,
		},
	}
}

// PooledConnection represents a connection in the pool
type PooledConnection struct {
	conn          *grpc.ClientConn
	client        proto.WorkerPoolClient
	lastUsed      time.Time
	inUse         bool
	id            string
}

// Pool manages a pool of gRPC connections to worker servers
type Pool struct {
	config      PoolConfig
	connections []*PooledConnection
	mutex       sync.RWMutex
	semaphore   chan struct{}
	log         *logger.Logger
	ctx         context.Context
	cancel      context.CancelFunc
}

// NewPool creates a new worker pool client
func NewPool(config PoolConfig, log *logger.Logger) (*Pool, error) {
	if config.MaxConnections <= 0 {
		config.MaxConnections = 10
	}
	if config.ConnectionTimeout <= 0 {
		config.ConnectionTimeout = 5 * time.Second
	}
	if config.KeepAliveInterval <= 0 {
		config.KeepAliveInterval = 30 * time.Second
	}

	ctx, cancel := context.WithCancel(context.Background())

	pool := &Pool{
		config:      config,
		connections: make([]*PooledConnection, 0, config.MaxConnections),
		semaphore:   make(chan struct{}, config.MaxConnections),
		log:         log,
		ctx:         ctx,
		cancel:      cancel,
	}

	// Initialize the semaphore
	for i := 0; i < config.MaxConnections; i++ {
		pool.semaphore <- struct{}{}
	}

	// Start background health check
	go pool.healthCheckLoop()

	return pool, nil
}

// Close gracefully shuts down the pool
func (p *Pool) Close() error {
	p.cancel()
	
	p.mutex.Lock()
	defer p.mutex.Unlock()

	var lastErr error
	for _, pc := range p.connections {
		if pc.conn != nil {
			if err := pc.conn.Close(); err != nil {
				p.log.Error("Failed to close connection", map[string]interface{}{
					"error": err.Error(),
					"conn_id": pc.id,
				})
				lastErr = err
			}
		}
	}

	p.connections = p.connections[:0]
	return lastErr
}

// getConnection acquires a connection from the pool
func (p *Pool) getConnection(ctx context.Context) (*PooledConnection, error) {
	// Wait for available slot
	select {
	case <-p.semaphore:
		// Got a slot
	case <-ctx.Done():
		return nil, fmt.Errorf("context cancelled while waiting for connection: %w", ctx.Err())
	case <-p.ctx.Done():
		return nil, fmt.Errorf("pool closed")
	}

	p.mutex.Lock()
	defer p.mutex.Unlock()

	// Try to find an existing available connection
	for _, pc := range p.connections {
		if !pc.inUse && p.isHealthy(pc) {
			pc.inUse = true
			pc.lastUsed = time.Now()
			return pc, nil
		}
	}

	// Create new connection if under limit
	if len(p.connections) < p.config.MaxConnections {
		pc, err := p.createConnection()
		if err != nil {
			// Release the semaphore slot
			p.semaphore <- struct{}{}
			return nil, err
		}
		pc.inUse = true
		pc.lastUsed = time.Now()
		p.connections = append(p.connections, pc)
		return pc, nil
	}

	// Should not reach here if semaphore is working correctly
	p.semaphore <- struct{}{}
	return nil, fmt.Errorf("no available connections in pool")
}

// releaseConnection returns a connection to the pool
func (p *Pool) releaseConnection(pc *PooledConnection) {
	p.mutex.Lock()
	pc.inUse = false
	pc.lastUsed = time.Now()
	p.mutex.Unlock()

	// Release the semaphore slot
	p.semaphore <- struct{}{}
}

// createConnection creates a new gRPC connection
func (p *Pool) createConnection() (*PooledConnection, error) {
	ctx, cancel := context.WithTimeout(p.ctx, p.config.ConnectionTimeout)
	defer cancel()

	conn, err := grpc.DialContext(ctx, p.config.Address,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithBlock(),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to worker server at %s: %w", p.config.Address, err)
	}

	client := proto.NewWorkerPoolClient(conn)

	pc := &PooledConnection{
		conn:     conn,
		client:   client,
		lastUsed: time.Now(),
		inUse:    false,
		id:       fmt.Sprintf("conn-%d", time.Now().UnixNano()),
	}

	p.log.Info("Created new connection to worker pool", map[string]interface{}{
		"address": p.config.Address,
		"conn_id": pc.id,
	})

	return pc, nil
}

// isHealthy checks if a connection is healthy
func (p *Pool) isHealthy(pc *PooledConnection) bool {
	if pc.conn == nil {
		return false
	}
	
	state := pc.conn.GetState()
	return state == connectivity.Ready || state == connectivity.Idle
}

// healthCheckLoop periodically checks connection health
func (p *Pool) healthCheckLoop() {
	ticker := time.NewTicker(p.config.KeepAliveInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			p.checkAndCleanupConnections()
		case <-p.ctx.Done():
			return
		}
	}
}

// checkAndCleanupConnections removes stale connections
func (p *Pool) checkAndCleanupConnections() {
	p.mutex.Lock()
	defer p.mutex.Unlock()

	activeConnections := make([]*PooledConnection, 0, len(p.connections))
	
	for _, pc := range p.connections {
		if pc.inUse {
			// Keep connections that are in use
			activeConnections = append(activeConnections, pc)
			continue
		}

		// Check if connection is healthy
		if p.isHealthy(pc) {
			activeConnections = append(activeConnections, pc)
		} else {
			// Close unhealthy connection
			if pc.conn != nil {
				pc.conn.Close()
			}
			p.log.Info("Closed unhealthy connection", map[string]interface{}{
				"conn_id": pc.id,
			})
		}
	}

	p.connections = activeConnections
}

// ExecuteTask executes a task on a worker with retry logic
func (p *Pool) ExecuteTask(ctx context.Context, req *proto.ExecuteTaskRequest) (*proto.ExecuteTaskResponse, error) {
	var lastErr error
	backoff := p.config.RetryPolicy.InitialBackoff

	for attempt := 0; attempt <= p.config.RetryPolicy.MaxRetries; attempt++ {
		if attempt > 0 {
			p.log.Info("Retrying ExecuteTask", map[string]interface{}{
				"attempt": attempt,
				"backoff": backoff.String(),
			})
			time.Sleep(backoff)
			backoff = time.Duration(float64(backoff) * p.config.RetryPolicy.BackoffMultiplier)
			if backoff > p.config.RetryPolicy.MaxBackoff {
				backoff = p.config.RetryPolicy.MaxBackoff
			}
		}

		pc, err := p.getConnection(ctx)
		if err != nil {
			lastErr = err
			continue
		}

		resp, err := pc.client.ExecuteTask(ctx, req)
		p.releaseConnection(pc)

		if err == nil {
			return resp, nil
		}

		lastErr = err
		p.log.Error("ExecuteTask failed", map[string]interface{}{
			"attempt": attempt + 1,
			"error":   err.Error(),
		})
	}

	return nil, fmt.Errorf("ExecuteTask failed after %d attempts: %w", p.config.RetryPolicy.MaxRetries+1, lastErr)
}

// GetPoolStatus gets the status of the worker pool
func (p *Pool) GetPoolStatus(ctx context.Context) (*proto.GetPoolStatusResponse, error) {
	pc, err := p.getConnection(ctx)
	if err != nil {
		return nil, err
	}
	defer p.releaseConnection(pc)

	return pc.client.GetPoolStatus(ctx, &proto.GetPoolStatusRequest{})
}

// ScalePool scales the worker pool
func (p *Pool) ScalePool(ctx context.Context, workerCount int32) (*proto.ScalePoolResponse, error) {
	pc, err := p.getConnection(ctx)
	if err != nil {
		return nil, err
	}
	defer p.releaseConnection(pc)

	req := &proto.ScalePoolRequest{
		WorkerCount: workerCount,
	}
	return pc.client.ScalePool(ctx, req)
}

// GetWorkerHealth gets the health of a specific worker
func (p *Pool) GetWorkerHealth(ctx context.Context, workerID string) (*proto.GetWorkerHealthResponse, error) {
	pc, err := p.getConnection(ctx)
	if err != nil {
		return nil, err
	}
	defer p.releaseConnection(pc)

	req := &proto.GetWorkerHealthRequest{
		WorkerId: workerID,
	}
	return pc.client.GetWorkerHealth(ctx, req)
}

// StreamTaskEvents streams task events from the worker pool
func (p *Pool) StreamTaskEvents(ctx context.Context) (proto.WorkerPool_StreamTaskEventsClient, error) {
	pc, err := p.getConnection(ctx)
	if err != nil {
		return nil, err
	}

	// Note: For streaming, we need to handle connection differently
	// The connection will be released when the stream ends
	stream, err := pc.client.StreamTaskEvents(ctx, &proto.StreamTaskEventsRequest{})
	if err != nil {
		p.releaseConnection(pc)
		return nil, err
	}

	// Return a wrapper that releases the connection when done
	return &streamWrapper{
		WorkerPool_StreamTaskEventsClient: stream,
		pool:                            p,
		pc:                              pc,
	}, nil
}

// streamWrapper wraps a stream client to handle connection release
type streamWrapper struct {
	proto.WorkerPool_StreamTaskEventsClient
	pool *Pool
	pc   *PooledConnection
}

// Recv overrides the Recv method to handle connection cleanup on error
func (s *streamWrapper) Recv() (*proto.TaskEvent, error) {
	event, err := s.WorkerPool_StreamTaskEventsClient.Recv()
	if err != nil {
		// Release connection on error
		s.pool.releaseConnection(s.pc)
	}
	return event, err
}

// GetStats returns statistics about the pool
func (p *Pool) GetStats() PoolStats {
	p.mutex.RLock()
	defer p.mutex.RUnlock()

	stats := PoolStats{
		TotalConnections: len(p.connections),
		MaxConnections:   p.config.MaxConnections,
	}

	for _, pc := range p.connections {
		if pc.inUse {
			stats.ActiveConnections++
		} else if p.isHealthy(pc) {
			stats.IdleConnections++
		} else {
			stats.UnhealthyConnections++
		}
	}

	return stats
}

// PoolStats contains statistics about the pool
type PoolStats struct {
	TotalConnections     int
	ActiveConnections    int
	IdleConnections      int
	UnhealthyConnections int
	MaxConnections       int
}
