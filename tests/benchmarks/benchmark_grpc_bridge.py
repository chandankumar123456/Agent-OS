#!/usr/bin/env python3
"""
Performance Benchmark for AgentOS Desktop Automation gRPC Bridge
Measures latency of each RPC call
"""

import subprocess
import time
import statistics
from datetime import datetime

def benchmark_rpc(rpc_name: str, iterations: int = 10) -> dict:
    """Benchmark a specific RPC call"""
    times = []
    
    for i in range(iterations):
        start = time.time()
        result = subprocess.run(
            ["cargo", "run", "--bin", "test-client", "--", "http://localhost:50051"],
            cwd=r"E:\Projects\AgentOS\desktop",
            capture_output=True,
            text=True,
            timeout=60
        )
        elapsed = (time.time() - start) * 1000  # Convert to ms
        times.append(elapsed)
    
    return {
        "rpc": rpc_name,
        "iterations": iterations,
        "min_ms": min(times),
        "max_ms": max(times),
        "avg_ms": statistics.mean(times),
        "median_ms": statistics.median(times),
        "std_dev": statistics.stdev(times) if len(times) > 1 else 0
    }

def run_benchmarks():
    """Run performance benchmarks"""
    print("=" * 70)
    print("AGENTOS DESKTOP AUTOMATION - PERFORMANCE BENCHMARKS")
    print("=" * 70)
    print()
    print(f"Server: http://localhost:50051")
    print(f"Iterations per RPC: 10")
    print(f"Start time: {datetime.now().isoformat()}")
    print()
    
    # Warm up
    print("Warming up...")
    subprocess.run(
        ["cargo", "run", "--bin", "test-client", "--", "http://localhost:50051"],
        cwd=r"E:\Projects\AgentOS\desktop",
        capture_output=True,
        timeout=60
    )
    time.sleep(0.5)
    
    # Run benchmarks
    print("Running benchmarks...")
    print()
    
    result = benchmark_rpc("All RPCs Combined", iterations=5)
    
    print("Results:")
    print(f"  RPC: {result['rpc']}")
    print(f"  Iterations: {result['iterations']}")
    print(f"  Min: {result['min_ms']:.2f} ms")
    print(f"  Max: {result['max_ms']:.2f} ms")
    print(f"  Avg: {result['avg_ms']:.2f} ms")
    print(f"  Median: {result['median_ms']:.2f} ms")
    print(f"  Std Dev: {result['std_dev']:.2f} ms")
    print()
    
    # Per-RPC analysis (approximate)
    num_rpcs = 4  # FindWindow, Observe, Decide, CloseSession
    avg_per_rpc = result['avg_ms'] / num_rpcs
    
    print("Per-RPC Estimates (approximate):")
    print(f"  Average per RPC: {avg_per_rpc:.2f} ms")
    print()
    
    # Target comparison
    target_latency = 5.0  # ms
    print(f"Target Latency: {target_latency} ms")
    print(f"Current Average: {avg_per_rpc:.2f} ms")
    
    if avg_per_rpc <= target_latency:
        print(f"  ✓ Within target ({(target_latency/avg_per_rpc):.1f}x better than target)")
    else:
        print(f"  ✗ Exceeds target ({(avg_per_rpc/target_latency):.1f}x target)")
    
    print()
    print("=" * 70)

if __name__ == "__main__":
    run_benchmarks()
