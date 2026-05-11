//! WebSocket event bridge between Supervisor and Tauri frontend.
//!
//! Connects to the Supervisor's WebSocket event endpoint and forwards
//! events to the frontend via Tauri's event system.

use futures_util::StreamExt;
use serde_json::Value;
use std::time::Duration;
use tauri::Manager;
use tokio_tungstenite::tungstenite;

const SUPERVISOR_WS_URL: &str = "ws://127.0.0.1:8080/api/v1/events";
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
                    eprintln!(
                        "Event bridge: {} — reconnecting in {}ms",
                        e, delay_ms
                    );
                }
            }

            tokio::time::sleep(Duration::from_millis(delay_ms)).await;
            delay_ms = (delay_ms * 2).min(RECONNECT_MAX_DELAY_MS);
        }
    });
}

/// Connects to the Supervisor WebSocket and forwards events to the frontend.
async fn connect_and_listen(
    app_handle: &tauri::AppHandle,
) -> Result<(), String> {
    use tokio_tungstenite::connect_async;

    let (ws_stream, _) = connect_async(SUPERVISOR_WS_URL)
        .await
        .map_err(|e| format!("WebSocket connect failed: {}", e))?;
    let (_write, read) = ws_stream.split();

    let mut messages = read;

    while let Some(msg_result) = messages.next().await {
        match msg_result.map_err(|e| format!("WebSocket recv error: {}", e))? {
            tungstenite::Message::Text(text) => {
                forward_event(app_handle, &text);
            }
            tungstenite::Message::Close(_) => {
                break;
            }
            _ => {}
        }
    }

    Ok(())
}

/// Forwards a JSON event from Supervisor to the Tauri frontend.
fn forward_event(app_handle: &tauri::AppHandle, text: &str) {
    match serde_json::from_str::<Value>(text) {
        Ok(event) => {
            // Emit generic event with full payload
            let _ = app_handle.emit_all("supervisor:event", &event);

            // Emit type-specific event for targeted listeners
            if let Some(event_type) = event.get("type").and_then(|t| t.as_str()) {
                let event_name = format!("supervisor:{}", event_type);
                if let Some(payload) = event.get("payload") {
                    let _ = app_handle.emit_all(&event_name, payload);
                }
            }
        }
        Err(e) => {
            eprintln!("Event bridge: failed to parse event JSON: {}", e);
        }
    }
}
