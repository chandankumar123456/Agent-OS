package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"github.com/google/uuid"
)

// AgentConfig represents a user-defined agent configuration
type AgentConfig struct {
	ID           string  `json:"id"`
	Name         string  `json:"name"`
	Description  string  `json:"description"`
	Role         string  `json:"role"`
	SystemPrompt string  `json:"system_prompt,omitempty"`
	Model        string  `json:"model,omitempty"`
	Temperature  float64 `json:"temperature,omitempty"`
	MaxTokens    int     `json:"max_tokens,omitempty"`
	Status       string  `json:"status"`
	CreatedAt    string  `json:"created_at"`
	UpdatedAt    string  `json:"updated_at"`
}

// ─── Agent Configuration Handlers (for /api/v1/agent-configs) ───────

// HandleListAgents handles GET for agent configs
func (s *Supervisor) HandleListAgents(w http.ResponseWriter, r *http.Request) {
	if s.db == nil {
		w.WriteHeader(http.StatusServiceUnavailable)
		json.NewEncoder(w).Encode(map[string]string{"error": "database not initialized"})
		return
	}

	rows, err := s.db.conn.Query(
		`SELECT id, name, description, role, COALESCE(system_prompt,''), COALESCE(model,''),
		        COALESCE(temperature,0.7), COALESCE(max_tokens,2048), status, created_at, updated_at
		 FROM agent_configs ORDER BY name`,
	)
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
		return
	}
	defer rows.Close()

	agents := []AgentConfig{}
	for rows.Next() {
		a := AgentConfig{}
		var createdAt, updatedAt time.Time
		err := rows.Scan(&a.ID, &a.Name, &a.Description, &a.Role, &a.SystemPrompt, &a.Model,
			&a.Temperature, &a.MaxTokens, &a.Status, &createdAt, &updatedAt)
		if err != nil {
			continue
		}
		a.CreatedAt = createdAt.Format(time.RFC3339)
		a.UpdatedAt = updatedAt.Format(time.RFC3339)
		agents = append(agents, a)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(agents)
}

// HandleCreateAgent handles POST for agent configs
func (s *Supervisor) HandleCreateAgent(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Name         string  `json:"name"`
		Description  string  `json:"description"`
		Role         string  `json:"role"`
		SystemPrompt string  `json:"system_prompt,omitempty"`
		Model        string  `json:"model,omitempty"`
		Temperature  float64 `json:"temperature,omitempty"`
		MaxTokens    int     `json:"max_tokens,omitempty"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{"error": "invalid request body"})
		return
	}

	if req.Name == "" {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{"error": "name is required"})
		return
	}
	if req.Role == "" {
		req.Role = "assistant"
	}
	if req.Temperature == 0 {
		req.Temperature = 0.7
	}
	if req.MaxTokens == 0 {
		req.MaxTokens = 2048
	}

	id := uuid.New().String()
	now := time.Now()

	_, err := s.db.conn.Exec(
		`INSERT INTO agent_configs (id, name, description, role, system_prompt, model, temperature, max_tokens, status, created_at, updated_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)`,
		id, req.Name, req.Description, req.Role, req.SystemPrompt, req.Model,
		req.Temperature, req.MaxTokens, now, now,
	)
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(AgentConfig{
		ID:           id,
		Name:         req.Name,
		Description:  req.Description,
		Role:         req.Role,
		SystemPrompt: req.SystemPrompt,
		Model:        req.Model,
		Temperature:  req.Temperature,
		MaxTokens:    req.MaxTokens,
		Status:       "active",
		CreatedAt:    now.Format(time.RFC3339),
		UpdatedAt:    now.Format(time.RFC3339),
	})
}

// ─── Agent Config Router (self-contained, correct path extraction) ──

// HandleAgentConfigRoute routes all /api/v1/agent-configs requests.
// Extracts the ID from the path correctly and calls internal methods.
func (s *Supervisor) HandleAgentConfigRoute(w http.ResponseWriter, r *http.Request) {
	prefix := "/api/v1/agent-configs"
	path := r.URL.Path[len(prefix):]
	// Strip leading slash
	if len(path) > 0 && path[0] == '/' {
		path = path[1:]
	}
	// Strip trailing slash
	if len(path) > 0 && path[len(path)-1] == '/' {
		path = path[:len(path)-1]
	}

	// No ID in path → list or create
	if path == "" {
		switch r.Method {
		case http.MethodGet:
			s.HandleListAgents(w, r)
		case http.MethodPost:
			s.HandleCreateAgent(w, r)
		default:
			w.WriteHeader(http.StatusMethodNotAllowed)
		}
		return
	}

	// ID present → get / update / delete
	agentID := path
	switch r.Method {
	case http.MethodGet:
		a, err := s.getAgentByID(agentID)
		if err != nil {
			w.WriteHeader(http.StatusNotFound)
			json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
			return
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(a)

	case http.MethodPut:
		var req struct {
			Name         string  `json:"name"`
			Description  string  `json:"description"`
			Role         string  `json:"role"`
			SystemPrompt string  `json:"system_prompt,omitempty"`
			Model        string  `json:"model,omitempty"`
			Temperature  float64 `json:"temperature,omitempty"`
			MaxTokens    int     `json:"max_tokens,omitempty"`
			Status       string  `json:"status,omitempty"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			w.WriteHeader(http.StatusBadRequest)
			json.NewEncoder(w).Encode(map[string]string{"error": "invalid request body"})
			return
		}
		now := time.Now()
		_, err := s.db.conn.Exec(
			`UPDATE agent_configs SET name=COALESCE(NULLIF(?,''),name), description=COALESCE(NULLIF(?,''),description),
			 role=COALESCE(NULLIF(?,''),role), system_prompt=COALESCE(NULLIF(?,''),system_prompt),
			 model=COALESCE(NULLIF(?,''),model), temperature=COALESCE(NULLIF(?,0),temperature),
			 max_tokens=COALESCE(NULLIF(?,0),max_tokens), status=COALESCE(NULLIF(?,''),status),
			 updated_at=? WHERE id=?`,
			req.Name, req.Description, req.Role, req.SystemPrompt, req.Model,
			req.Temperature, req.MaxTokens, req.Status, now, agentID,
		)
		if err != nil {
			w.WriteHeader(http.StatusInternalServerError)
			json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
			return
		}
		a, err := s.getAgentByID(agentID)
		if err != nil {
			w.WriteHeader(http.StatusNotFound)
			json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
			return
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(a)

	case http.MethodDelete:
		result, err := s.db.conn.Exec(`DELETE FROM agent_configs WHERE id=?`, agentID)
		if err != nil {
			w.WriteHeader(http.StatusInternalServerError)
			json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
			return
		}
		affected, _ := result.RowsAffected()
		if affected == 0 {
			w.WriteHeader(http.StatusNotFound)
			json.NewEncoder(w).Encode(map[string]string{"error": fmt.Sprintf("agent %s not found", agentID)})
			return
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]string{"message": "agent deleted"})

	default:
		w.WriteHeader(http.StatusMethodNotAllowed)
	}
}

func (s *Supervisor) getAgentByID(id string) (*AgentConfig, error) {
	a := &AgentConfig{}
	var createdAt, updatedAt time.Time
	err := s.db.conn.QueryRow(
		`SELECT id, name, description, role, COALESCE(system_prompt,''), COALESCE(model,''),
		        COALESCE(temperature,0.7), COALESCE(max_tokens,2048), status, created_at, updated_at
		 FROM agent_configs WHERE id=?`,
		id,
	).Scan(&a.ID, &a.Name, &a.Description, &a.Role, &a.SystemPrompt, &a.Model,
		&a.Temperature, &a.MaxTokens, &a.Status, &createdAt, &updatedAt)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("agent %s not found", id)
		}
		return nil, err
	}
	a.CreatedAt = createdAt.Format(time.RFC3339)
	a.UpdatedAt = updatedAt.Format(time.RFC3339)
	return a, nil
}
