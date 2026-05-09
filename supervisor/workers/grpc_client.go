// Package workers provides a high-performance worker pool for task execution
// using Go goroutines for true parallelism, replacing Python asyncio workers.
package workers

import (
	"context"
	"fmt"
	"time"

	pb "github.com/AgentOS/supervisor/proto"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/keepalive"
)

// GrpcClient wraps a gRPC connection to the Python executor
type GrpcClient struct {
	conn    *grpc.ClientConn
	client  pb.WorkerPoolClient
	timeout time.Duration
}

// NewGrpcClient creates a new gRPC client connection to the Python executor
func NewGrpcClient(address string, timeout time.Duration) (*GrpcClient, error) {
	if timeout == 0 {
		timeout = 30 * time.Second
	}

	// Configure keepalive parameters for connection health
	keepaliveParams := keepalive.ClientParameters{
		Time:                10 * time.Second,
		Timeout:             5 * time.Second,
		PermitWithoutStream: true,
	}

	// Create gRPC connection with insecure credentials (for localhost)
	conn, err := grpc.Dial(
		address,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithKeepaliveParams(keepaliveParams),
		grpc.WithBlock(),
		grpc.WithTimeout(timeout),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to executor at %s: %w", address, err)
	}

	// Create the client
	client := pb.NewWorkerPoolClient(conn)

	return &GrpcClient{
		conn:    conn,
		client:  client,
		timeout: timeout,
	}, nil
}

// ExecuteTask sends a task execution request to the Python executor
func (c *GrpcClient) ExecuteTask(ctx context.Context, req *pb.ExecuteTaskRequest) (*pb.ExecuteTaskResponse, error) {
	// Use timeout from request if specified, otherwise use client default
	timeout := c.timeout
	if req.TimeoutMs > 0 {
		timeout = time.Duration(req.TimeoutMs) * time.Millisecond
	}

	// Create timeout context
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	// Call the ExecuteTask RPC
	resp, err := c.client.ExecuteTask(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("execute task RPC failed: %w", err)
	}

	return resp, nil
}

// GetPoolStatus retrieves the current status of the worker pool
func (c *GrpcClient) GetPoolStatus(ctx context.Context) (*pb.GetPoolStatusResponse, error) {
	ctx, cancel := context.WithTimeout(ctx, c.timeout)
	defer cancel()

	req := &pb.GetPoolStatusRequest{}
	resp, err := c.client.GetPoolStatus(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("get pool status RPC failed: %w", err)
	}

	return resp, nil
}

// ScalePool requests the pool to scale to a target number of workers
func (c *GrpcClient) ScalePool(ctx context.Context, targetWorkers int32, reason string) (*pb.ScalePoolResponse, error) {
	ctx, cancel := context.WithTimeout(ctx, c.timeout)
	defer cancel()

	req := &pb.ScalePoolRequest{
		TargetWorkers: targetWorkers,
		Reason:        reason,
	}
	resp, err := c.client.ScalePool(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("scale pool RPC failed: %w", err)
	}

	return resp, nil
}

// GetWorkerHealth retrieves health information for a specific worker
func (c *GrpcClient) GetWorkerHealth(ctx context.Context, workerID string) (*pb.GetWorkerHealthResponse, error) {
	ctx, cancel := context.WithTimeout(ctx, c.timeout)
	defer cancel()

	req := &pb.GetWorkerHealthRequest{
		WorkerId: workerID,
	}
	resp, err := c.client.GetWorkerHealth(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("get worker health RPC failed: %w", err)
	}

	return resp, nil
}

// StreamTaskEvents creates a stream of task events from the executor
func (c *GrpcClient) StreamTaskEvents(ctx context.Context, taskID string) (pb.WorkerPool_StreamTaskEventsClient, error) {
	req := &pb.StreamTaskEventsRequest{
		TaskId: taskID,
	}

	stream, err := c.client.StreamTaskEvents(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("stream task events RPC failed: %w", err)
	}

	return stream, nil
}

// Close closes the gRPC connection
func (c *GrpcClient) Close() error {
	if c.conn != nil {
		return c.conn.Close()
	}
	return nil
}

// IsConnected returns true if the client has an active connection
func (c *GrpcClient) IsConnected() bool {
	if c.conn == nil {
		return false
	}
	state := c.conn.GetState()
	return state == grpc.Ready || state == grpc.Idle
}

// GetConnectionState returns the current connection state
func (c *GrpcClient) GetConnectionState() grpc.ConnectivityState {
	if c.conn == nil {
		return grpc.Shutdown
	}
	return c.conn.GetState()
}
