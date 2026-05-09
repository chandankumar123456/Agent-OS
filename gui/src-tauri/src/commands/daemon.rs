use tauri::command;
use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize)]
pub struct DaemonStatus {
    pub running: bool,
    pub version: String,
}

#[command]
pub async fn get_daemon_status() -> Result<DaemonStatus, String> {
    // TODO: Implement actual daemon status check via HTTP API
    Ok(DaemonStatus {
        running: true,
        version: "0.1.0".to_string(),
    })
}

#[command]
pub async fn start_daemon() -> Result<(), String> {
    // TODO: Implement daemon start via supervisor
    println!("Starting daemon...");
    Ok(())
}

#[command]
pub async fn stop_daemon() -> Result<(), String> {
    // TODO: Implement daemon stop
    println!("Stopping daemon...");
    Ok(())
}
