//! gRPC streaming event bridge between kernel and Tauri frontend.
//!
//! Connects to the kernel's gRPC streaming endpoint and forwards
//! events to the frontend via Tauri's event system.

use std::time::Duration;
use tauri::Manager;
use tokio_stream::StreamExt;

use agentos_ipc_client::KernelClient;

const RECONNECT_BASE_DELAY_MS: u64 = 1000;
const RECONNECT_MAX_DELAY_MS: u64 = 30000;

/// Starts the event bridge background task.
pub fn start_event_bridge(app_handle: tauri::AppHandle) {
    tokio::spawn(async move {
        let mut delay_ms = RECONNECT_BASE_DELAY_MS;

        loop {
            match connect_and_listen(&app_handle).await {
                Ok(()) => {
                    delay_ms = RECONNECT_BASE_DELAY_MS;
                }
                Err(e) => {
                    tracing::debug!(
                        "Event bridge: {} - reconnecting in {}ms",
                        e, delay_ms
                    );
                }
            }

            tokio::time::sleep(Duration::from_millis(delay_ms)).await;
            delay_ms = (delay_ms * 2).min(RECONNECT_MAX_DELAY_MS);
        }
    });
}

/// Connects to the kernel gRPC stream and forwards events to the frontend.
async fn connect_and_listen(app_handle: &tauri::AppHandle) -> Result<(), String> {
    let mut client = KernelClient::connect()
        .await
        .map_err(|e| format!("gRPC connect failed: {}", e))?;

    // Stream all events (empty task_id means all tasks)
    let mut stream = client
        .stream_events("", true)
        .await
        .map_err(|e| format!("stream_events RPC failed: {}", e))?;

    while let Some(event_result) = stream.next().await {
        match event_result {
            Ok(event) => {
                forward_event(app_handle, &event);
            }
            Err(e) => {
                return Err(format!("Stream error: {}", e));
            }
        }
    }

    Ok(())
}

/// Forwards a gRPC TaskEvent to the Tauri frontend.
fn forward_event(
    app_handle: &tauri::AppHandle,
    event: &agentos_ipc_client::runtime::TaskEvent,
) {
    // Serialize the event to JSON for the frontend
    let payload = serde_json::json!({
        "task_id": event.task_id,
        "event_type": event.event_type,
        "error": event.error,
    });

    // Emit generic event with full payload
    let _ = app_handle.emit_all("kernel:event", &payload);

    // Emit type-specific event
    let event_name = format!("kernel:event:{}", event.event_type);
    let _ = app_handle.emit_all(&event_name, &payload);
}
