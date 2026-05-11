use tauri::command;
use serde::{Deserialize, Serialize};

const APP_NAME: &str = "AgentOS";

#[derive(Debug, Serialize, Deserialize)]
pub struct SecretResult {
    pub success: bool,
    pub value: Option<String>,
    pub error: Option<String>,
}

fn get_entry(key: &str) -> Result<keyring::Entry, String> {
    keyring::Entry::new(APP_NAME, key).map_err(|e| format!("Failed to access keychain: {}", e))
}

#[command]
pub fn get_secret(key: String) -> SecretResult {
    match get_entry(&key) {
        Ok(entry) => match entry.get_password() {
            Ok(value) => SecretResult {
                success: true,
                value: Some(value),
                error: None,
            },
            Err(keyring::Error::NoEntry) => SecretResult {
                success: true,
                value: None,
                error: None,
            },
            Err(e) => SecretResult {
                success: false,
                value: None,
                error: Some(format!("Failed to get secret: {}", e)),
            },
        },
        Err(e) => SecretResult {
            success: false,
            value: None,
            error: Some(e),
        },
    }
}

#[command]
pub fn set_secret(key: String, value: String) -> SecretResult {
    match get_entry(&key) {
        Ok(entry) => match entry.set_password(&value) {
            Ok(_) => SecretResult {
                success: true,
                value: Some(value),
                error: None,
            },
            Err(e) => SecretResult {
                success: false,
                value: None,
                error: Some(format!("Failed to set secret: {}", e)),
            },
        },
        Err(e) => SecretResult {
            success: false,
            value: None,
            error: Some(e),
        },
    }
}

#[command]
pub fn delete_secret(key: String) -> SecretResult {
    match get_entry(&key) {
            Ok(entry) => match entry.delete_credential() {
            Ok(_) => SecretResult {
                success: true,
                value: None,
                error: None,
            },
            Err(keyring::Error::NoEntry) => SecretResult {
                success: true,
                value: None,
                error: None,
            },
            Err(e) => SecretResult {
                success: false,
                value: None,
                error: Some(format!("Failed to delete secret: {}", e)),
            },
        },
        Err(e) => SecretResult {
            success: false,
            value: None,
            error: Some(e),
        },
    }
}
