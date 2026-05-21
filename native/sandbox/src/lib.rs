//! Process sandbox for AgentOS
//!
//! This crate is a stub for future migration of OS-level process isolation.
//! It will eventually provide secure sandboxing for agent-spawned processes using
//! platform-specific mechanisms:
//!
//! - Linux: cgroups + seccomp-bpf
//! - macOS: sandbox-exec (seatbelt)
//! - Windows: Job Objects + restricted tokens
//!
//! The Python-side sandbox (`core/tools/sandbox.py`) is NOT being migrated in this
//! phase; this crate provides the Rust-native interface that will replace it in a
//! future phase.

use std::collections::HashMap;
use std::path::PathBuf;

/// Configuration for a sandboxed process
#[derive(Debug, Clone)]
pub struct SandboxConfig {
    /// Working directory for the sandboxed process
    pub working_dir: PathBuf,
    /// Environment variables to set
    pub env: HashMap<String, String>,
    /// Maximum memory in bytes (0 = unlimited)
    pub max_memory_bytes: u64,
    /// Maximum CPU time in seconds (0 = unlimited)
    pub max_cpu_seconds: u64,
    /// Whether network access is allowed
    pub allow_network: bool,
    /// Allowed filesystem paths (read-only)
    pub readonly_paths: Vec<PathBuf>,
    /// Allowed filesystem paths (read-write)
    pub writable_paths: Vec<PathBuf>,
}

impl Default for SandboxConfig {
    fn default() -> Self {
        Self {
            working_dir: PathBuf::from("."),
            env: HashMap::new(),
            max_memory_bytes: 0,
            max_cpu_seconds: 0,
            allow_network: false,
            readonly_paths: Vec::new(),
            writable_paths: Vec::new(),
        }
    }
}

/// Result of a sandboxed process execution
#[derive(Debug, Clone)]
pub struct SandboxResult {
    /// Process exit code
    pub exit_code: i32,
    /// Captured stdout
    pub stdout: Vec<u8>,
    /// Captured stderr
    pub stderr: Vec<u8>,
    /// Wall-clock duration in milliseconds
    pub duration_ms: u64,
    /// Whether the process was killed due to resource limits
    pub killed: bool,
}

/// Errors that can occur during sandboxed execution
#[derive(thiserror::Error, Debug)]
pub enum SandboxError {
    #[error("Failed to spawn process: {0}")]
    SpawnFailed(String),
    #[error("Sandbox setup failed: {0}")]
    SetupFailed(String),
    #[error("Process exceeded resource limits: {0}")]
    ResourceLimitExceeded(String),
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
    #[error("Platform not supported for sandboxing: {0}")]
    UnsupportedPlatform(String),
}

/// Trait defining the sandbox interface for process isolation.
///
/// Implementations provide platform-specific sandboxing using OS primitives
/// to restrict what spawned processes can access.
pub trait Sandbox: Send + Sync {
    /// Spawn a sandboxed process with the given command and arguments.
    ///
    /// The process will be constrained according to the provided `SandboxConfig`.
    /// Returns a `SandboxResult` with captured output and exit information.
    fn spawn(
        &self,
        command: &str,
        args: &[&str],
        config: &SandboxConfig,
    ) -> Result<SandboxResult, SandboxError>;
}

/// OS-level process sandbox using platform-native isolation primitives.
///
/// TODO: Implement platform-specific isolation per the migration plan:
/// - Linux: cgroups v2 for resource limits, seccomp-bpf for syscall filtering
/// - macOS: sandbox-exec profiles for filesystem/network restrictions
/// - Windows: Job Objects for resource limits, restricted tokens for access control
pub struct OsProcessSandbox;

impl OsProcessSandbox {
    /// Create a new OS process sandbox instance
    pub fn new() -> Self {
        Self
    }
}

impl Default for OsProcessSandbox {
    fn default() -> Self {
        Self::new()
    }
}

impl Sandbox for OsProcessSandbox {
    fn spawn(
        &self,
        command: &str,
        args: &[&str],
        config: &SandboxConfig,
    ) -> Result<SandboxResult, SandboxError> {
        // TODO(phase-9): Implement platform-specific sandboxing
        // For now, spawn without isolation as a baseline implementation.
        // This matches the current Python sandbox behavior which also runs
        // processes without kernel-level isolation.
        self.spawn_unsandboxed(command, args, config)
    }
}

impl OsProcessSandbox {
    /// Spawn a process without sandbox isolation (baseline implementation).
    /// This is a temporary implementation until platform-specific sandboxing is added.
    fn spawn_unsandboxed(
        &self,
        command: &str,
        args: &[&str],
        config: &SandboxConfig,
    ) -> Result<SandboxResult, SandboxError> {
        use std::process::Command;
        use std::time::Instant;

        tracing::warn!(
            "Spawning process without sandbox isolation (not yet implemented): {} {:?}",
            command,
            args
        );

        let start = Instant::now();

        let mut cmd = Command::new(command);
        cmd.args(args).current_dir(&config.working_dir);

        for (key, value) in &config.env {
            cmd.env(key, value);
        }

        let output = cmd.output().map_err(|e| {
            SandboxError::SpawnFailed(format!("Failed to execute {}: {}", command, e))
        })?;

        let duration_ms = start.elapsed().as_millis() as u64;

        Ok(SandboxResult {
            exit_code: output.status.code().unwrap_or(-1),
            stdout: output.stdout,
            stderr: output.stderr,
            duration_ms,
            killed: false,
        })
    }

    /// Linux-specific sandbox setup using cgroups + seccomp
    #[cfg(target_os = "linux")]
    #[allow(dead_code)]
    fn setup_linux_sandbox(&self, _config: &SandboxConfig) -> Result<(), SandboxError> {
        // TODO: Implement cgroups v2 resource limits
        // TODO: Implement seccomp-bpf syscall filtering
        unimplemented!("Linux sandbox with cgroups/seccomp not yet implemented")
    }

    /// macOS-specific sandbox setup using sandbox-exec
    #[cfg(target_os = "macos")]
    #[allow(dead_code)]
    fn setup_macos_sandbox(&self, _config: &SandboxConfig) -> Result<(), SandboxError> {
        // TODO: Generate sandbox-exec profile from SandboxConfig
        // TODO: Use sandbox_init or sandbox-exec wrapper
        unimplemented!("macOS sandbox with sandbox-exec not yet implemented")
    }

    /// Windows-specific sandbox setup using Job Objects
    #[cfg(target_os = "windows")]
    #[allow(dead_code)]
    fn setup_windows_sandbox(&self, _config: &SandboxConfig) -> Result<(), SandboxError> {
        // TODO: Create Job Object with resource limits
        // TODO: Create restricted token for access control
        unimplemented!("Windows sandbox with Job Objects not yet implemented")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sandbox_config_default() {
        let config = SandboxConfig::default();
        assert_eq!(config.max_memory_bytes, 0);
        assert_eq!(config.max_cpu_seconds, 0);
        assert!(!config.allow_network);
    }

    #[test]
    fn test_os_process_sandbox_spawn() {
        let sandbox = OsProcessSandbox::new();
        let config = SandboxConfig::default();

        let result = sandbox.spawn("echo", &["hello"], &config);
        assert!(result.is_ok());

        let result = result.unwrap();
        assert_eq!(result.exit_code, 0);
        assert!(!result.killed);
        assert!(String::from_utf8_lossy(&result.stdout).contains("hello"));
    }

    #[test]
    fn test_sandbox_spawn_nonexistent_command() {
        let sandbox = OsProcessSandbox::new();
        let config = SandboxConfig::default();

        let result = sandbox.spawn("nonexistent_command_xyz", &[], &config);
        assert!(result.is_err());
    }
}
