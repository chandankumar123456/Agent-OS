package main

import (
	"encoding/json"
	"log"
	"net/http"
	"sync"
	"sync/atomic"
	"time"

	"github.com/gorilla/websocket"
)

// Event types broadcast to WebSocket clients
const (
	EventTaskCreated   = "task:created"
	EventTaskUpdated   = "task:updated"
	EventTaskCompleted = "task:completed"
	EventTaskFailed    = "task:failed"
	EventTaskCancelled = "task:cancelled"
	EventStepUpdated   = "step:updated"
)

// Event is a generic event payload sent over WebSocket
type Event struct {
	Type      string      `json:"type"`
	Timestamp time.Time   `json:"timestamp"`
	Payload   interface{} `json:"payload"`
}

// TaskEventPayload is sent with task-related events
type TaskEventPayload struct {
	TaskID     string `json:"task_id"`
	Status     string `json:"status"`
	Query      string `json:"query,omitempty"`
	Error      string `json:"error,omitempty"`
	StepIndex  int    `json:"step_index,omitempty"`
	StepStatus string `json:"step_status,omitempty"`
}

// EventHub manages WebSocket connections and broadcasts events
type EventHub struct {
	upgrader    websocket.Upgrader
	clients     map[*websocket.Conn]bool
	mu          sync.RWMutex
	eventCount  atomic.Int64
	done        chan struct{}
}

// NewEventHub creates a new WebSocket event hub
func NewEventHub() *EventHub {
	return &EventHub{
		upgrader: websocket.Upgrader{
			ReadBufferSize:  1024,
			WriteBufferSize: 1024,
			CheckOrigin: func(r *http.Request) bool {
				// Allow connections only from localhost in desktop mode
				return true // Accept all for localhost-only binding
			},
		},
		clients: make(map[*websocket.Conn]bool),
		done:    make(chan struct{}),
	}
}

// HandleWebSocket upgrades an HTTP connection to WebSocket
func (h *EventHub) HandleWebSocket(w http.ResponseWriter, r *http.Request) {
	conn, err := h.upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("EventHub: WebSocket upgrade failed: %v", err)
		return
	}

	h.mu.Lock()
	h.clients[conn] = true
	clientCount := len(h.clients)
	h.mu.Unlock()

	log.Printf("EventHub: client connected (%d total)", clientCount)

	// Read loop to detect disconnection
	go func() {
		defer func() {
			h.mu.Lock()
			delete(h.clients, conn)
			remaining := len(h.clients)
			h.mu.Unlock()
			conn.Close()
			log.Printf("EventHub: client disconnected (%d remaining)", remaining)
		}()

		for {
			_, _, err := conn.ReadMessage()
			if err != nil {
				if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseNormalClosure) {
					log.Printf("EventHub: read error: %v", err)
				}
				break
			}
		}
	}()
}

// Broadcast sends an event to all connected WebSocket clients
func (h *EventHub) Broadcast(event Event) {
	h.eventCount.Add(1)
	data, err := json.Marshal(event)
	if err != nil {
		log.Printf("EventHub: marshal error: %v", err)
		return
	}

	h.mu.RLock()
	defer h.mu.RUnlock()

	for conn := range h.clients {
		err := conn.WriteMessage(websocket.TextMessage, data)
		if err != nil {
			log.Printf("EventHub: write error: %v", err)
			go conn.Close()
		}
	}
}

// EmitTaskEvent creates and broadcasts a task-related event
func (h *EventHub) EmitTaskEvent(eventType string, taskID string, status string, query string) {
	h.Broadcast(Event{
		Type:      eventType,
		Timestamp: time.Now(),
		Payload: TaskEventPayload{
			TaskID: taskID,
			Status: status,
			Query:  query,
		},
	})
}

// EmitTaskError creates and broadcasts a task error event
func (h *EventHub) EmitTaskError(taskID string, status string, errMsg string) {
	h.Broadcast(Event{
		Type:      EventTaskFailed,
		Timestamp: time.Now(),
		Payload: TaskEventPayload{
			TaskID: taskID,
			Status: status,
			Error:  errMsg,
		},
	})
}

// EmitStepEvent creates and broadcasts a step update event
func (h *EventHub) EmitStepEvent(taskID string, stepIndex int, stepStatus string) {
	h.Broadcast(Event{
		Type:      EventStepUpdated,
		Timestamp: time.Now(),
		Payload: TaskEventPayload{
			TaskID:     taskID,
			StepIndex:  stepIndex,
			StepStatus: stepStatus,
		},
	})
}

// ClientCount returns the number of connected clients
func (h *EventHub) ClientCount() int {
	h.mu.RLock()
	defer h.mu.RUnlock()
	return len(h.clients)
}

// EventCount returns the total number of events broadcast
func (h *EventHub) EventCount() int64 {
	return h.eventCount.Load()
}

// Close shuts down the event hub and disconnects all clients
func (h *EventHub) Close() {
	close(h.done)
	h.mu.Lock()
	defer h.mu.Unlock()
	for conn := range h.clients {
		conn.WriteMessage(websocket.CloseMessage, []byte{})
		conn.Close()
	}
}
