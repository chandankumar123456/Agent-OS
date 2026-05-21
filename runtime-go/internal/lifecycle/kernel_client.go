package lifecycle

import (
	"context"
	"fmt"
	"log"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	pb "github.com/AgentOS/agentos-runtime/internal/proto/runtime"
)

// KernelClient wraps gRPC calls to the Python core kernel
type KernelClient struct {
	conn    *grpc.ClientConn
	client  pb.RuntimeServiceClient
	address string
}

// NewKernelClient creates a new kernel client targeting the given address
func NewKernelClient(address string) *KernelClient {
	return &KernelClient{
		address: address,
	}
}

// Connect establishes the gRPC connection with retries
func (kc *KernelClient) Connect(ctx context.Context, maxRetries int) error {
	var lastErr error

	for i := 0; i < maxRetries; i++ {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		conn, err := grpc.NewClient(kc.address,
			grpc.WithTransportCredentials(insecure.NewCredentials()),
		)
		if err != nil {
			lastErr = err
			log.Printf("gRPC client connection attempt %d/%d failed: %v, retrying in 1s...", i+1, maxRetries, err)
			time.Sleep(1 * time.Second)
			continue
		}

		client := pb.NewRuntimeServiceClient(conn)

		// Test connection with health check
		healthCtx, cancel := context.WithTimeout(ctx, 2*time.Second)
		_, lastErr = client.HealthCheck(healthCtx, &pb.HealthCheckRequest{})
		cancel()

		if lastErr == nil {
			kc.conn = conn
			kc.client = client
			log.Printf("gRPC client connected to Python kernel at %s", kc.address)
			return nil
		}

		conn.Close()
		log.Printf("gRPC client health check attempt %d/%d failed: %v, retrying in 1s...", i+1, maxRetries, lastErr)
		time.Sleep(1 * time.Second)
	}

	return fmt.Errorf("failed to connect to kernel after %d attempts: %w", maxRetries, lastErr)
}

// HealthCheck probes the kernel's health endpoint
func (kc *KernelClient) HealthCheck(ctx context.Context) (bool, error) {
	if kc.client == nil {
		return false, fmt.Errorf("client not connected")
	}

	resp, err := kc.client.HealthCheck(ctx, &pb.HealthCheckRequest{})
	if err != nil {
		return false, err
	}

	return resp.Healthy, nil
}

// GetRuntimeStatus queries the kernel's runtime status
func (kc *KernelClient) GetRuntimeStatus(ctx context.Context) error {
	if kc.client == nil {
		return fmt.Errorf("client not connected")
	}

	_, err := kc.client.GetRuntimeStatus(ctx, &pb.GetRuntimeStatusRequest{
		IncludeMetrics: true,
	})
	return err
}

// Shutdown requests the kernel to shut down gracefully
func (kc *KernelClient) Shutdown(ctx context.Context, graceful bool, timeoutSec int32) error {
	if kc.client == nil {
		return fmt.Errorf("client not connected")
	}

	_, err := kc.client.Shutdown(ctx, &pb.ShutdownRequest{
		Graceful:       graceful,
		TimeoutSeconds: timeoutSec,
	})
	return err
}

// IsConnected returns whether the client has an active connection
func (kc *KernelClient) IsConnected() bool {
	return kc.client != nil
}

// Close closes the gRPC connection
func (kc *KernelClient) Close() error {
	if kc.conn != nil {
		return kc.conn.Close()
	}
	return nil
}
