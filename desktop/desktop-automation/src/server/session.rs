//! Session management for desktop automation
//! Tracks active sessions and their state

use std::collections::HashMap;
use std::time::{Duration, Instant};

/// Session state
#[derive(Debug, Clone)]
pub struct Session {
    pub id: String,
    pub created_at: Instant,
    pub last_activity: Instant,
    pub state: SessionState,
    pub metadata: HashMap<String, String>,
}

/// Session state enum
#[derive(Debug, Clone, PartialEq)]
pub enum SessionState {
    Active,
    Waiting,
    Executing,
    Completed,
    Failed,
    Recovering,
}

/// Session manager
pub struct SessionManager {
    sessions: HashMap<String, Session>,
    timeout: Duration,
}

impl SessionManager {
    pub fn new() -> Self {
        Self {
            sessions: HashMap::new(),
            timeout: Duration::from_secs(300), // 5 minute default timeout
        }
    }

    /// Create a new session
    pub fn create_session(&mut self, session_id: String) -> &Session {
        let now = Instant::now();
        let session = Session {
            id: session_id.clone(),
            created_at: now,
            last_activity: now,
            state: SessionState::Active,
            metadata: HashMap::new(),
        };
        self.sessions.insert(session_id, session);
        self.sessions.get(&session_id).unwrap()
    }

    /// Get a session by ID
    pub fn get_session(&self, session_id: &str) -> Option<&Session> {
        self.sessions.get(session_id)
    }

    /// Update session state
    pub fn update_state(&mut self, session_id: &str, state: SessionState) {
        if let Some(session) = self.sessions.get_mut(session_id) {
            session.state = state;
            session.last_activity = Instant::now();
        }
    }

    /// Update session metadata
    pub fn update_metadata(&mut self, session_id: &str, key: &str, value: &str) {
        if let Some(session) = self.sessions.get_mut(session_id) {
            session.metadata.insert(key.to_string(), value.to_string());
            session.last_activity = Instant::now();
        }
    }

    /// Remove a session
    pub fn remove_session(&mut self, session_id: &str) {
        self.sessions.remove(session_id);
    }

    /// Get all active sessions
    pub fn get_active_sessions(&self) -> Vec<&Session> {
        self.sessions
            .values()
            .filter(|s| s.state == SessionState::Active || s.state == SessionState::Executing)
            .collect()
    }

    /// Clean up expired sessions
    pub fn cleanup_expired(&mut self) -> usize {
        let now = Instant::now();
        let expired: Vec<String> = self
            .sessions
            .iter()
            .filter(|(_, s)| now.duration_since(s.last_activity) > self.timeout)
            .map(|(id, _)| id.clone())
            .collect();

        for id in &expired {
            self.sessions.remove(id);
        }

        expired.len()
    }

    /// Get session count
    pub fn session_count(&self) -> usize {
        self.sessions.len()
    }
}

impl Default for SessionManager {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_session_creation() {
        let mut manager = SessionManager::new();
        manager.create_session("test-session".to_string());
        
        assert_eq!(manager.session_count(), 1);
        assert!(manager.get_session("test-session").is_some());
    }

    #[test]
    fn test_session_removal() {
        let mut manager = SessionManager::new();
        manager.create_session("test-session".to_string());
        manager.remove_session("test-session");
        
        assert_eq!(manager.session_count(), 0);
    }

    #[test]
    fn test_session_state_update() {
        let mut manager = SessionManager::new();
        manager.create_session("test-session".to_string());
        manager.update_state("test-session", SessionState::Executing);
        
        let session = manager.get_session("test-session").unwrap();
        assert_eq!(session.state, SessionState::Executing);
    }
}