use tauri::command;
use tauri::PackageInfo;

#[command]
pub fn get_app_version(package_info: PackageInfo) -> Result<String, String> {
    Ok(package_info.version.to_string())
}
