//! IPC Protocol definitions for AgentOS
//!
//! This crate provides generated Rust types and gRPC client/server stubs for all
//! AgentOS IPC contracts. The canonical .proto files live at the top-level `proto/`
//! directory and cover:
//!
//! - `runtime` - Primary Go supervisor <-> Python runtime interface
//! - `checkpoint` - Persistent state management via SQLite
//! - `worker` - Task execution between Go worker pool and Python executor
//! - `desktop` - Desktop automation (Windows UI automation)

/// Runtime service protocol (Go supervisor <-> Python runtime)
pub mod runtime {
    tonic::include_proto!("runtime");
}

/// Checkpoint service protocol (persistent state management)
pub mod checkpoint {
    tonic::include_proto!("checkpoint");
}

/// Worker executor protocol (task execution)
pub mod worker {
    tonic::include_proto!("worker");
}

/// Desktop automation protocol (Windows UI automation)
pub mod desktop {
    tonic::include_proto!("desktop_protocol");
}
