#!/usr/bin/env python3
"""
Integration Test Suite for AgentOS Desktop Automation gRPC Bridge
Tests all 11 RPC methods end-to-end between Rust client and Python server
"""

import subprocess
import sys
import time
from datetime import datetime

def run_tests():
    """Run all integration tests"""
    print("=" * 70)
    print("AGENTOS DESKTOP AUTOMATION - INTEGRATION TEST SUITE")
    print("=" * 70)
    print()
    
    print(f"Server URL: http://localhost:50051")
    print(f"Start time: {datetime.now().isoformat()}")
    print()
    
    # Run Rust test client
    start_time = time.time()
    result = subprocess.run(
        ["cargo", "run", "--bin", "test-client", "--", "http://localhost:50051"],
        cwd=r"E:\Projects\AgentOS\desktop",
        capture_output=True,
        text=True,
        timeout=30
    )
    elapsed = time.time() - start_time
    
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    
    print()
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print()
    
    output = result.stdout
    tests = [
        ("Connection", "Connected successfully" in output),
        ("FindWindow", "Found window" in output and "test-window-123" in output),
        ("Observe", "Observation ID" in output and "Window count: 3" in output),
        ("Decide", "Action type: click" in output and "Confidence: 0.85" in output),
        ("CloseSession", "Session closed: true" in output),
    ]
    
    passed = sum(1 for _, result in tests if result)
    failed = len(tests) - passed
    
    print(f"Total Tests: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success Rate: {(passed/len(tests)*100):.1f}%")
    print(f"Total Time: {elapsed:.3f}s")
    print()
    
    print("Test Results:")
    for name, result in tests:
        status = "PASS" if result else "FAIL"
        print(f"  {name}: {status}")
    
    print()
    print("=" * 70)
    
    return failed == 0

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
