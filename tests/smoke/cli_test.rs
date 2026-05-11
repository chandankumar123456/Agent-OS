#[cfg(test)]
mod smoke_tests {
    use std::process::Command;

    #[test]
    #[cfg(target_os = "windows")]
    fn test_cli_binary_exists() {
        // Verify the CLI binary can be built and shows help
        let output = Command::new("cargo")
            .args(["build", "--release"])
            .current_dir("../../cli")
            .output()
            .expect("Failed to build CLI");

        assert!(
            output.status.success(),
            "CLI build failed: {}",
            String::from_utf8_lossy(&output.stderr)
        );
    }

    #[test]
    #[cfg(target_os = "windows")]
    fn test_cli_help_command() {
        // Verify the CLI binary exists and responds to --help
        let binary_path = if cfg!(target_os = "windows") {
            "../../cli/target/release/agentos.exe"
        } else {
            "../../cli/target/release/agentos"
        };

        if !std::path::Path::new(binary_path).exists() {
            // Build first
            let _ = Command::new("cargo")
                .args(["build", "--release"])
                .current_dir("../../cli")
                .output();
        }

        if !std::path::Path::new(binary_path).exists() {
            panic!("CLI binary not found at {}", binary_path);
        }

        let output = Command::new(binary_path)
            .arg("--help")
            .output()
            .expect("Failed to run CLI --help");

        assert!(output.status.success(), "CLI --help failed");

        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(
            stdout.contains("AgentOS") || stdout.contains("USAGE"),
            "CLI help output missing expected content"
        );
    }
}
