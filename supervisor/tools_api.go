package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"
)

// ToolDefinition represents a registered tool in the system
type ToolDefinition struct {
	ID               string `json:"id"`
	Name             string `json:"name"`
	Description      string `json:"description"`
	Category         string `json:"category"`
	Type             string `json:"type"`
	Status           string `json:"status"`
	ParametersSchema string `json:"parameters_schema,omitempty"`
	CreatedAt        string `json:"created_at"`
	UpdatedAt        string `json:"updated_at"`
}

// HandleListTools handles GET /api/v1/tools
func (s *Supervisor) HandleListTools(w http.ResponseWriter, r *http.Request) {
	if s.db == nil {
		w.WriteHeader(http.StatusServiceUnavailable)
		json.NewEncoder(w).Encode(map[string]string{"error": "database not initialized"})
		return
	}

	category := r.URL.Query().Get("category")
	var query string
	var args []interface{}

	if category != "" && category != "All" {
		query = `SELECT id, name, description, category, type, status, COALESCE(parameters_schema,'{}'), created_at, updated_at
		         FROM tool_definitions WHERE category=? ORDER BY name`
		args = append(args, category)
	} else {
		query = `SELECT id, name, description, category, type, status, COALESCE(parameters_schema,'{}'), created_at, updated_at
		         FROM tool_definitions ORDER BY category, name`
	}

	rows, err := s.db.conn.Query(query, args...)
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
		return
	}
	defer rows.Close()

	tools := []ToolDefinition{}
	for rows.Next() {
		t := ToolDefinition{}
		var createdAt, updatedAt time.Time
		err := rows.Scan(&t.ID, &t.Name, &t.Description, &t.Category, &t.Type,
			&t.Status, &t.ParametersSchema, &createdAt, &updatedAt)
		if err != nil {
			continue
		}
		t.CreatedAt = createdAt.Format(time.RFC3339)
		t.UpdatedAt = updatedAt.Format(time.RFC3339)
		tools = append(tools, t)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(tools)
}

// HandleGetTool handles GET /api/v1/tools/{name}
func (s *Supervisor) HandleGetTool(w http.ResponseWriter, r *http.Request) {
	toolName := extractPathParam(r.URL.Path, "/api/v1/tools/")
	if toolName == "" {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{"error": "tool name required"})
		return
	}

	t, err := s.getToolByName(toolName)
	if err != nil {
		w.WriteHeader(http.StatusNotFound)
		json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(t)
}

// HandleListToolCategories handles GET /api/v1/tools/categories
func (s *Supervisor) HandleListToolCategories(w http.ResponseWriter, r *http.Request) {
	if s.db == nil {
		w.WriteHeader(http.StatusServiceUnavailable)
		json.NewEncoder(w).Encode(map[string]string{"error": "database not initialized"})
		return
	}

	rows, err := s.db.conn.Query(`SELECT DISTINCT category FROM tool_definitions ORDER BY category`)
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
		return
	}
	defer rows.Close()

	categories := []string{"All"}
	for rows.Next() {
		var cat string
		if err := rows.Scan(&cat); err == nil {
			categories = append(categories, cat)
		}
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{"categories": categories})
}

// HandleCreateTool handles POST /api/v1/tools
func (s *Supervisor) HandleCreateTool(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Name             string `json:"name"`
		Description      string `json:"description"`
		Category         string `json:"category"`
		Type             string `json:"type"`
		ParametersSchema string `json:"parameters_schema,omitempty"`
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
	if req.Category == "" {
		req.Category = "general"
	}
	if req.Type == "" {
		req.Type = "custom"
	}
	if req.ParametersSchema == "" {
		req.ParametersSchema = "{}"
	}

	id := uuid.New().String()
	now := time.Now()

	_, err := s.db.conn.Exec(
		`INSERT INTO tool_definitions (id, name, description, category, type, status, parameters_schema, created_at, updated_at)
		 VALUES (?, ?, ?, ?, ?, 'available', ?, ?, ?)`,
		id, req.Name, req.Description, req.Category, req.Type, req.ParametersSchema, now, now,
	)
	if err != nil {
		if strings.Contains(err.Error(), "UNIQUE") {
			w.WriteHeader(http.StatusConflict)
			json.NewEncoder(w).Encode(map[string]string{"error": fmt.Sprintf("tool '%s' already exists", req.Name)})
			return
		}
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(ToolDefinition{
		ID:               id,
		Name:             req.Name,
		Description:      req.Description,
		Category:         req.Category,
		Type:             req.Type,
		Status:           "available",
		ParametersSchema: req.ParametersSchema,
		CreatedAt:        now.Format(time.RFC3339),
		UpdatedAt:        now.Format(time.RFC3339),
	})
}

// HandleToolRoute routes tool requests
func (s *Supervisor) HandleToolRoute(w http.ResponseWriter, r *http.Request) {
	prefix := "/api/v1/tools"
	path := r.URL.Path[len(prefix):]

	switch {
	case path == "" || path == "/":
		switch r.Method {
		case http.MethodGet:
			s.HandleListTools(w, r)
		case http.MethodPost:
			s.HandleCreateTool(w, r)
		default:
			w.WriteHeader(http.StatusMethodNotAllowed)
		}
	case path == "/categories" || path == "/categories/":
		s.HandleListToolCategories(w, r)
	default:
		// /api/v1/tools/{name}
		if r.Method == http.MethodGet {
			s.HandleGetTool(w, r)
		} else {
			w.WriteHeader(http.StatusMethodNotAllowed)
		}
	}
}

func (s *Supervisor) getToolByName(name string) (*ToolDefinition, error) {
	t := &ToolDefinition{}
	var createdAt, updatedAt time.Time
	err := s.db.conn.QueryRow(
		`SELECT id, name, description, category, type, status, COALESCE(parameters_schema,'{}'), created_at, updated_at
		 FROM tool_definitions WHERE name=?`,
		name,
	).Scan(&t.ID, &t.Name, &t.Description, &t.Category, &t.Type,
		&t.Status, &t.ParametersSchema, &createdAt, &updatedAt)
	if err != nil {
		return nil, fmt.Errorf("tool '%s' not found", name)
	}
	t.CreatedAt = createdAt.Format(time.RFC3339)
	t.UpdatedAt = updatedAt.Format(time.RFC3339)
	return t, nil
}
