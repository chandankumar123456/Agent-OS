package lifecycle

import (
	"encoding/json"
	"log"
	"sync"
	"sync/atomic"
	"time"
)

// Event types broadcast to internal subscribers
const (
	EventProcessStarted  = "process:started"
	EventProcessStopped  = "process:stopped"
	EventProcessCrashed  = "process:crashed"
	EventHealthChanged   = "health:changed"
	EventUpdateAvailable = "update:available"
)

// Event is a generic event payload
type Event struct {
	Type      string      `json:"type"`
	Timestamp time.Time   `json:"timestamp"`
	Payload   interface{} `json:"payload"`
}

// ProcessEventPayload is sent with process lifecycle events
type ProcessEventPayload struct {
	ProcessName string `json:"process_name"`
	Status      string `json:"status"`
	Error       string `json:"error,omitempty"`
	PID         int    `json:"pid,omitempty"`
}

// EventHandler is a function that handles events
type EventHandler func(event Event)

// EventHub manages internal lifecycle event broadcasting
type EventHub struct {
	subscribers map[string][]EventHandler
	mu          sync.RWMutex
	eventCount  atomic.Int64
	done        chan struct{}
}

// NewEventHub creates a new event hub
func NewEventHub() *EventHub {
	return &EventHub{
		subscribers: make(map[string][]EventHandler),
		done:        make(chan struct{}),
	}
}

// Subscribe registers a handler for a specific event type
func (h *EventHub) Subscribe(eventType string, handler EventHandler) {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.subscribers[eventType] = append(h.subscribers[eventType], handler)
}

// Publish sends an event to all subscribers of that event type
func (h *EventHub) Publish(event Event) {
	h.eventCount.Add(1)

	h.mu.RLock()
	handlers := h.subscribers[event.Type]
	allHandlers := h.subscribers["*"] // wildcard subscribers
	h.mu.RUnlock()

	for _, handler := range handlers {
		handler(event)
	}
	for _, handler := range allHandlers {
		handler(event)
	}
}

// EmitProcessEvent creates and publishes a process lifecycle event
func (h *EventHub) EmitProcessEvent(eventType string, processName string, status string, errMsg string) {
	h.Publish(Event{
		Type:      eventType,
		Timestamp: time.Now(),
		Payload: ProcessEventPayload{
			ProcessName: processName,
			Status:      status,
			Error:       errMsg,
		},
	})
}

// EventCount returns the total number of events published
func (h *EventHub) EventCount() int64 {
	return h.eventCount.Load()
}

// MarshalEvent marshals an event to JSON
func MarshalEvent(event Event) ([]byte, error) {
	data, err := json.Marshal(event)
	if err != nil {
		log.Printf("EventHub: marshal error: %v", err)
		return nil, err
	}
	return data, nil
}

// Close shuts down the event hub
func (h *EventHub) Close() {
	close(h.done)
}
