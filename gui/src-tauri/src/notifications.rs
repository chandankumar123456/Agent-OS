use tauri::api::notification::Notification;
use tauri::AppHandle;

pub fn notify_task_completed(app: &AppHandle, task_id: &str, result: &str) {
    let _ = Notification::new(app.config().tauri.bundle.identifier.clone())
        .title("AgentOS - Task Completed")
        .body(format!("Task {} completed\n{}", &task_id[..8.min(task_id.len())], result))
        .show();
}

pub fn notify_task_failed(app: &AppHandle, task_id: &str, error: &str) {
    let _ = Notification::new(app.config().tauri.bundle.identifier.clone())
        .title("AgentOS - Task Failed")
        .body(format!("Task {} failed\n{}", &task_id[..8.min(task_id.len())], error))
        .show();
}

pub fn notify_approval_required(app: &AppHandle, task_id: &str, action: &str) {
    let _ = Notification::new(app.config().tauri.bundle.identifier.clone())
        .title("AgentOS - Approval Required")
        .body(format!("Task {} requires approval for: {}", &task_id[..8.min(task_id.len())], action))
        .show();
}

pub fn notify_recovery_triggered(app: &AppHandle, task_id: &str, attempt: u32) {
    let _ = Notification::new(app.config().tauri.bundle.identifier.clone())
        .title("AgentOS - Recovery Triggered")
        .body(format!("Task {} - Recovery attempt {}", &task_id[..8.min(task_id.len())], attempt))
        .show();
}
