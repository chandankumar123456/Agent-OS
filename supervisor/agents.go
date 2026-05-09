package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"time"

	"github.com/google/uuid"
)

// AgentSession represents an agent execution session
type AgentSession struct {
	ID          string    `json:"id"`
	AgentID     string    `json:"agent_id"`
	Status      string    `json:"status"`
	Input       string    `json:"input,omitempty"`
	Output      string    `json:"output,omitempty"`
	ErrorMessage string   `json:"error_message,omitempty"`
	StartedAt   *time.Time `json:"started_at,omitempty"`
	CompletedAt *time.Time `json:"completed_at,omitempty"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

// Action represents an action taken during a session
type Action struct {
	ID           string    `json:"id"`
	SessionID    string    `json:"session_id"`
	Sequence     int       `json:"sequence"`
	ActionType   string    `json:"action_type"`
	Target       string    `json:"target,omitempty"`
	Arguments    string    `json:"arguments,omitempty"`
	Status       string    `json:"status"`
	Result       string    `json:"result,omitempty"`
	ErrorMessage string    `json:"error_message,omitempty"`
	CreatedAt    time.Time `json:"created_at"`
}

// AgentSessionStore provides database operations for agent sessions
type AgentSessionStore struct {
	db *DB
}

// NewAgentSessionStore creates a new session store
func NewAgentSessionStore(db *DB) *AgentSessionStore {
	return &AgentSessionStore{db: db}
}

// CreateSession creates a new agent session
func (s *AgentSessionStore) CreateSession(agentID, input string) (*AgentSession, error) {
	sessionID := uuid.New().String()
	now := time.Now()

	_, err := s.db.conn.Exec(
		`INSERT INTO agent_sessions (id, agent_id, status, input, started_at, created_at, updated_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?)`,
		sessionID, agentID, "pending", input, now, now, now,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create session: %w", err)
	}

	return &AgentSession{
		ID:        sessionID,
		AgentID:   agentID,
		Status:    "pending",
		Input:     input,
		CreatedAt: now,
		UpdatedAt: now,
	}, nil
}

// GetSession retrieves a session by ID
func (s *AgentSessionStore) GetSession(sessionID string) (*AgentSession, error) {
	session := &AgentSession{}
	err := s.db.conn.QueryRow(
		`SELECT id, agent_id, status, input, output, error_message, started_at, completed_at, created_at, updated_at
		 FROM agent_sessions WHERE id = ?`,
		sessionID,
	).Scan(
		&session.ID, &session.AgentID, &session.Status, &session.Input, &session.Output,
		&session.ErrorMessage, &session.StartedAt, &session.CompletedAt, &session.CreatedAt, &session.UpdatedAt,
	)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("session not found: %s", sessionID)
		}
		return nil, fmt.Errorf("failed to get session: %w", err)
	}
	return session, nil
}

// UpdateSession updates a session's status and output
func (s *AgentSessionStore) UpdateSession(sessionID, status, output, errorMessage string) error {
	now := time.Now()
	_, err := s.db.conn.Exec(
		`UPDATE agent_sessions SET status = ?, output = ?, error_message = ?, completed_at = ?, updated_at = ?
		 WHERE id = ?`,
		status, output, errorMessage, now, now, sessionID,
	)
	if err != nil {
		return fmt.Errorf("failed to update session: %w", err)
	}
	return nil
}

// ListSessions lists sessions with optional filtering
func (s *AgentSessionStore) ListSessions(agentID, status string, limit int) ([]AgentSession, error) {
	query := `SELECT id, agent_id, status, input, output, error_message, started_at, completed_at, created_at, updated_at
			  FROM agent_sessions`
	args := []interface{}{}
	if agentID != "" || status != "" {
		query += " WHERE"
		if agentID != "" {
			query += " agent_id = ?"
			args = append(args, agentID)
		}
		if status != "" {
			if len(args) > 0 {
				query += " AND"
			}
			query += " status = ?"
			args = append(args, status)
		}
	}
	query += " ORDER BY created_at DESC LIMIT ?"
	args = append(args, limit)

	rows, err := s.db.conn.Query(query, args...)
	if err != nil {
		return nil, fmt.Errorf("failed to list sessions: %w", err)
	}
	defer rows.Close()

	sessions := []AgentSession{}
	for rows.Next() {
		session := AgentSession{}
		err := rows.Scan(
			&session.ID, &session.AgentID, &session.Status, &session.Input, &session.Output,
			&session.ErrorMessage, &session.StartedAt, &session.CompletedAt, &session.CreatedAt, &session.UpdatedAt,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan session: %w", err)
		}
		sessions = append(sessions, session)
	}

	return sessions, nil
}

// CreateAction creates a new action for a session
func (s *AgentSessionStore) CreateAction(sessionID string, sequence int, actionType, target, arguments string) (*Action, error) {
	actionID := uuid.New().String()
	now := time.Now()

	_, err := s.db.conn.Exec(
		`INSERT INTO actions (id, session_id, sequence, action_type, target, arguments, status, created_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
		actionID, sessionID, sequence, actionType, target, arguments, "pending", now,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create action: %w", err)
	}

	return &Action{
		ID:         actionID,
		SessionID:  sessionID,
		Sequence:   sequence,
		ActionType: actionType,
		Target:     target,
		Arguments:  arguments,
		Status:     "pending",
		CreatedAt:  now,
	}, nil
}

// UpdateAction updates an action's status and result
func (s *AgentSessionStore) UpdateAction(actionID, status, result, errorMessage string) error {
	_, err := s.db.conn.Exec(
		`UPDATE actions SET status = ?, result = ?, error_message = ? WHERE id = ?`,
		status, result, errorMessage, actionID,
	)
	if err != nil {
		return fmt.Errorf("failed to update action: %w", err)
	}
	return nil
}

// GetSessionActions retrieves all actions for a session
func (s *AgentSessionStore) GetSessionActions(sessionID string) ([]Action, error) {
	rows, err := s.db.conn.Query(
		`SELECT id, session_id, sequence, action_type, target, arguments, status, result, error_message, created_at
		 FROM actions WHERE session_id = ? ORDER BY sequence`,
		sessionID,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to get actions: %w", err)
	}
	defer rows.Close()

	actions := []Action{}
	for rows.Next() {
		action := Action{}
		err := rows.Scan(
			&action.ID, &action.SessionID, &action.Sequence, &action.ActionType, &action.Target,
			&action.Arguments, &action.Status, &action.Result, &action.ErrorMessage, &action.CreatedAt,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan action: %w", err)
		}
		actions = append(actions, action)
	}

	return actions, nil
}

// DeleteSession deletes a session by ID
func (s *AgentSessionStore) DeleteSession(sessionID string) error {
	// First delete all actions for this session
	_, err := s.db.conn.Exec(`DELETE FROM actions WHERE session_id = ?`, sessionID)
	if err != nil {
		return fmt.Errorf("failed to delete actions: %w", err)
	}

	// Then delete the session
	_, err = s.db.conn.Exec(`DELETE FROM agent_sessions WHERE id = ?`, sessionID)
	if err != nil {
		return fmt.Errorf("failed to delete session: %w", err)
	}

	return nil
}

// HandleCreateSession handles creating a new agent session
func (s *Supervisor) HandleCreateSession(w http.ResponseWriter, r *http.Request) {
	var req struct {
		AgentID string `json:"agent_id"`
		Input   string `json:"input"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{"error": "invalid request body"})
		return
	}

	if req.AgentID == "" {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{"error": "agent_id is required"})
		return
	}

	session, err := s.agentStore.CreateSession(req.AgentID, req.Input)
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(session)
}

// HandleGetSession handles getting a session by ID
func (s *Supervisor) HandleGetSession(w http.ResponseWriter, r *http.Request) {
	sessionID := r.PathValue("id")
	if sessionID == "" {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{"error": "session_id is required"})
		return
	}

	session, err := s.agentStore.GetSession(sessionID)
	if err != nil {
		w.WriteHeader(http.StatusNotFound)
		json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(session)
}

// HandleListSessions handles listing sessions
func (s *Supervisor) HandleListSessions(w http.ResponseWriter, r *http.Request) {
	agentID := r.URL.Query().Get("agent_id")
	status := r.URL.Query().Get("status")
	limit := 100

	sessions, err := s.agentStore.ListSessions(agentID, status, limit)
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(sessions)
}

// HandleUpdateSession handles updating a session
func (s *Supervisor) HandleUpdateSession(w http.ResponseWriter, r *http.Request) {
	sessionID := r.PathValue("id")
	if sessionID == "" {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{"error": "session_id is required"})
		return
	}

	var req struct {
		Status       string `json:"status"`
		Output       string `json:"output,omitempty"`
		ErrorMessage string `json:"error_message,omitempty"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{"error": "invalid request body"})
		return
	}

	if err := s.agentStore.UpdateSession(sessionID, req.Status, req.Output, req.ErrorMessage); err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"message": "session updated"})
}

// HandleDeleteSession handles deleting a session
func (s *Supervisor) HandleDeleteSession(w http.ResponseWriter, r *http.Request) {
	sessionID := r.PathValue("id")
	if sessionID == "" {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{"error": "session_id is required"})
		return
	}

	// Delete the session
	if err := s.agentStore.DeleteSession(sessionID); err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"message": "session deleted"})
}

// HandleCreateAction handles creating a new action
func (s *Supervisor) HandleCreateAction(w http.ResponseWriter, r *http.Request) {
	sessionID := r.PathValue("session_id")
	if sessionID == "" {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{"error": "session_id is required"})
		return
	}

	var req struct {
		Sequence   int    `json:"sequence"`
		ActionType string `json:"action_type"`
		Target     string `json:"target,omitempty"`
		Arguments  string `json:"arguments,omitempty"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{"error": "invalid request body"})
		return
	}

	action, err := s.agentStore.CreateAction(sessionID, req.Sequence, req.ActionType, req.Target, req.Arguments)
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(action)
}

// HandleGetSessionActions handles getting actions for a session
func (s *Supervisor) HandleGetSessionActions(w http.ResponseWriter, r *http.Request) {
	sessionID := r.PathValue("session_id")
	if sessionID == "" {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{"error": "session_id is required"})
		return
	}

	actions, err := s.agentStore.GetSessionActions(sessionID)
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(actions)
}

// InitializeAgentStore initializes the agent session store
func (s *Supervisor) InitializeAgentStore() error {
	store := NewAgentSessionStore(s.db)
	s.agentStore = store
	log.Println("Agent session store initialized")
	return nil
}
