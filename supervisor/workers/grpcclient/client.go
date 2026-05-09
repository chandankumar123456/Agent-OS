package grpcclient

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

// RetryConfig defines configuration for retry logic
type RetryConfig struct {
	// MaxRetries is the maximum number of retry attempts
	MaxRetries int
	// InitialBackoff is the initial backoff duration
	InitialBackoff time.Duration
	// MaxBackoff is the maximum backoff duration
	MaxBackoff time.Duration
	// BackoffMultiplier is the multiplier for exponential backoff
	BackoffMultiplier float64
}

// DefaultRetryConfig returns a default retry configuration
func DefaultRetryConfig() RetryConfig {
	return RetryConfig{
		MaxRetries:        5,
		InitialBackoff:    100 * time.Millisecond,
		MaxBackoff:        30 * time.Second,
		BackoffMultiplier: 2.0,
	}
}

// Client is a gRPC client with connection pooling and retry logic
type Client struct {
	address      string
	conn         *grpc.ClientConn
	client       proto.WorkerExecutorClient
	log          *logger.Logger
	retryConfig  RetryConfig
	metrics      Metrics
	mutex        sync.RWMutex
	ctx          context.Context
	cancel       context.CancelFunc
}

// Metrics tracks client performance metrics
type Metrics struct {
	TotalRequests    int64
	SuccessfulRequests int64
	FailedRequests   int64
	TotalLatency     time.Duration
	mu               sync.RWMutex
}

// Option is a functional option for configuring the Client
type Option func(*Client)

// WithRetryConfig sets the retry configuration
func WithRetryConfig(config RetryConfig) Option {
	return func(c *Client) {
		c.retryConfig = config
	}
}

// NewClient creates a new gRPC client with connection pooling
func NewClient(address string, log *logger.Logger, opts ...Option) (*Client, error) {
	ctx, cancel := context.WithCancel(context.Background())

	client := &Client{
		address:     address,
		log:         log,
		retryConfig: DefaultRetryConfig(),
		ctx:         ctx,
		cancel:      cancel,
	}

	// Apply options
	for _, opt := range opts {
		opt(client)
	}

	// Connect with retry
	if err := client.connectWithRetry(); err != nil {
		cancel()
		return nil, err
	}

	return client, nil
}

// connectWithRetry attempts to connect with exponential backoff
func (c *Client) connectWithRetry() error {
	backoff := c.retryConfig.InitialBackoff

	for attempt := 0; attempt <= c.retryConfig.MaxRetries; attempt++ {
		if attempt > 0 {
			c.log.Info("Retrying connection", map[string]interface{}{
				"attempt": attempt,
				"backoff": backoff.String(),
				"address": c.address,
			})
			time.Sleep(backoff)
			backoff = time.Duration(float64(backoff) * c.retryConfig.BackoffMultiplier)
			if backoff > c.retryConfig.MaxBackoff {
				backoff = c.retryConfig.MaxBackoff
			}
		}

		ctx, cancel := context.WithTimeout(c.ctx, 10*time.Second)
		conn, err := grpc.DialContext(ctx, c.address,
			grpc.WithTransportCredentials(insecure.NewCredentials()),
			grpc.WithBlock(),
		)
		cancel()

	if err == nil {
		c.mutex.Lock()
		c.conn = conn
		c.client = proto.NewWorkerExecutorClient(conn)
		c.mutex.Unlock()

			c.log.Info("Successfully connected to worker pool", map[string]interface{}{
				"address": c.address,
				"attempts": attempt + 1,
			})
			return nil
		}

		c.log.Error("Connection attempt failed", map[string]interface{}{
			"attempt": attempt + 1,
			"error":   err.Error(),
			"address": c.address,
		})
	}

	return fmt.Errorf("failed to connect after %d attempts", c.retryConfig.MaxRetries+1)
}

// Close closes the client connection
func (c *Client) Close() error {
	c.cancel()
	c.mutex.Lock()
	defer c.mutex.Unlock()

	if c.conn != nil {
		return c.conn.Close()
	}
	return nil
}

// IsConnected returns true if the client is connected
func (c *Client) IsConnected() bool {
	c.mutex.RLock()
	defer c.mutex.RUnlock()

	if c.conn == nil {
		return false
	}

	state := c.conn.GetState()
	return state == connectivity.Ready || state == connectivity.Idle
}

// ExecuteTask executes a task on a worker with retry logic
func (c *Client) ExecuteTask(ctx context.Context, req *proto.TaskRequest) (*proto.TaskResponse, error) {
	start := time.Now()
	defer func() {
		c.recordMetrics(time.Since(start))
	}()

	return c.ExecuteTaskWithRetry(ctx, req)
}

// ExecuteTaskWithRetry executes a task with automatic retry on transient errors
func (c *Client) ExecuteTaskWithRetry(ctx context.Context, req *proto.TaskRequest) (*proto.TaskResponse, error) {
	var lastErr error
	backoff := c.retryConfig.InitialBackoff

	for attempt := 0; attempt <= c.retryConfig.MaxRetries; attempt++ {
		if attempt > 0 {
			c.log.Info("Retrying task execution", map[string]interface{}{
				"attempt": attempt,
				"backoff": backoff.String(),
				"task_id": req.TaskId,
			})
			
			// Check context cancellation
			select {
			case <-ctx.Done():
				return nil, fmt.Errorf("context cancelled during retry: %w", ctx.Err())
			case <-time.After(backoff):
				// Continue with retry
			}
			
			backoff = time.Duration(float64(backoff) * c.retryConfig.BackoffMultiplier)
			if backoff > c.retryConfig.MaxBackoff {
				backoff = c.retryConfig.MaxBackoff
			}
		}

		c.mutex.RLock()
		client := c.client
		c.mutex.RUnlock()

		if client == nil {
			lastErr = fmt.Errorf("client not connected")
			continue
		}

		resp, err := client.ExecuteTask(ctx, req)
		if err == nil {
			c.incrementSuccessfulRequests()
			return resp, nil
		}

		lastErr = err
		c.incrementFailedRequests()
		
		if !c.isRetryableError(err) {
			return nil, err
		}

		c.log.Error("Task execution failed, will retry", map[string]interface{}{
			"attempt": attempt + 1,
			"task_id": req.TaskId,
			"error":   err.Error(),
		})
	}

	return nil, fmt.Errorf("task execution failed after %d attempts: %w", c.retryConfig.MaxRetries+1, lastErr)
}

// StreamTaskEvents streams task events from the worker pool
// Note: This is a placeholder - streaming is not yet implemented in the proto definition
func (c *Client) StreamTaskEvents(ctx context.Context) error {
	return fmt.Errorf("streaming not yet implemented")
}

// HealthCheck performs a health check on the connection
func (c *Client) HealthCheck(ctx context.Context) error {
	c.mutex.RLock()
	conn := c.conn
	c.mutex.RUnlock()

	if conn == nil {
		return fmt.Errorf("client not connected")
	}

	state := conn.GetState()
	if state != connectivity.Ready && state != connectivity.Idle {
		return fmt.Errorf("connection not ready: %v", state)
	}

	return nil
}

// isRetryableError determines if an error is retryable
func (c *Client) isRetryableError(err error) bool {
	// For now, retry all errors except context cancellation
	if err == nil {
		return false
	}
	
	// Check for context cancellation
	select {
	case <-c.ctx.Done():
		return false
	default:
	}

	// In a real implementation, we'd check for specific gRPC error codes
	// that indicate transient failures (Unavailable, ResourceExhausted, etc.)
	return true
}

// recordMetrics records request metrics
func (c *Client) recordMetrics(latency time.Duration) {
	c.metrics.mu.Lock()
	defer c.metrics.mu.Unlock()

	c.metrics.TotalRequests++
	c.metrics.TotalLatency += latency
}

// incrementSuccessfulRequests increments the successful request count
func (c *Client) incrementSuccessfulRequests() {
	c.metrics.mu.Lock()
	defer c.metrics.mu.Unlock()

	c.metrics.SuccessfulRequests++
}

// incrementFailedRequests increments the failed request count
func (c *Client) incrementFailedRequests() {
	c.metrics.mu.Lock()
	defer c.metrics.mu.Unlock()

	c.metrics.FailedRequests++
}

// GetMetrics returns the current metrics
func (c *Client) GetMetrics() Metrics {
	c.metrics.mu.RLock()
	defer c.metrics.mu.RUnlock()

	return Metrics{
		TotalRequests:      c.metrics.TotalRequests,
		SuccessfulRequests: c.metrics.SuccessfulRequests,
		FailedRequests:     c.metrics.FailedRequests,
		TotalLatency:       c.metrics.TotalLatency,
	}
}
