use tauri::command;
use tauri::AppHandle;
use crate::notifications;

#[command]
pub fn show_notification(app: AppHandle, title: String, body: String) -> Result<(), String> {
    let _ = tauri::api::notification::Notification::new(app.config().tauri.bundle.identifier.clone())
        .title(&title)
        .body(&body)
        .show();
    Ok(())
}
