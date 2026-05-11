package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
)

// pythonBaseURL is the base URL of the Python FastAPI backend
const pythonBaseURL = "http://127.0.0.1:8000"

// proxyToPython forwards an HTTP request to the Python FastAPI backend
// and returns the response to the original caller.
func (s *Supervisor) proxyToPython(w http.ResponseWriter, r *http.Request, path string) {
	pythonURL := pythonBaseURL + path

	// Read the original request body
	var bodyBytes []byte
	if r.Body != nil {
		bodyBytes, _ = io.ReadAll(r.Body)
		r.Body.Close()
	}

	// Create forwarded request
	proxyReq, err := http.NewRequest(r.Method, pythonURL, bytes.NewReader(bodyBytes))
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": "failed to create proxy request"})
		return
	}

	// Copy original query params
	proxyReq.URL.RawQuery = r.URL.RawQuery

	// Forward headers
	proxyReq.Header.Set("Content-Type", "application/json")
	if s.apiKey != "" {
		proxyReq.Header.Set("X-API-Key", s.apiKey)
	}

	// Send request to Python backend
	client := &http.Client{}
	resp, err := client.Do(proxyReq)
	if err != nil {
		w.WriteHeader(http.StatusBadGateway)
		json.NewEncoder(w).Encode(map[string]string{
			"error": fmt.Sprintf("Python backend unavailable: %v", err),
			"hint":  "Make sure the Python runtime is running (port 8000)",
		})
		return
	}
	defer resp.Body.Close()

	// Copy response headers
	for k, v := range resp.Header {
		w.Header()[k] = v
	}
	w.WriteHeader(resp.StatusCode)

	// Copy response body
	io.Copy(w, resp.Body)
}

// HandleDesktopScreenshot handles GET /api/v1/desktop/screenshot
func (s *Supervisor) HandleDesktopScreenshot(w http.ResponseWriter, r *http.Request) {
	// Forward to Python backend's screenshot endpoint
	// The Python FastAPI desktop endpoint captures via mss/pyautogui
	path := "/api/v1/desktop/screenshot"
	if r.URL.RawQuery != "" {
		path += "?" + r.URL.RawQuery
	}
	s.proxyToPython(w, r, path)
}

// HandleDesktopClick handles POST /api/v1/desktop/click
func (s *Supervisor) HandleDesktopClick(w http.ResponseWriter, r *http.Request) {
	s.proxyToPython(w, r, "/api/v1/desktop/click")
}

// HandleDesktopType handles POST /api/v1/desktop/type
func (s *Supervisor) HandleDesktopType(w http.ResponseWriter, r *http.Request) {
	s.proxyToPython(w, r, "/api/v1/desktop/type")
}

// HandleDesktopFocus handles POST /api/v1/desktop/focus
func (s *Supervisor) HandleDesktopFocus(w http.ResponseWriter, r *http.Request) {
	s.proxyToPython(w, r, "/api/v1/desktop/focus")
}

// HandleDesktopListWindows handles GET /api/v1/desktop/windows
func (s *Supervisor) HandleDesktopListWindows(w http.ResponseWriter, r *http.Request) {
	path := "/api/v1/desktop/windows"
	if r.URL.RawQuery != "" {
		path += "?" + r.URL.RawQuery
	}
	s.proxyToPython(w, r, path)
}

// HandleDesktopFind handles POST /api/v1/desktop/find
func (s *Supervisor) HandleDesktopFind(w http.ResponseWriter, r *http.Request) {
	s.proxyToPython(w, r, "/api/v1/desktop/find")
}

// HandleDesktopRoute routes desktop action requests
func (s *Supervisor) HandleDesktopRoute(w http.ResponseWriter, r *http.Request) {
	// /api/v1/desktop/screenshot
	// /api/v1/desktop/click
	// /api/v1/desktop/type
	// /api/v1/desktop/focus
	// /api/v1/desktop/windows
	// /api/v1/desktop/find
	path := r.URL.Path
	action := strings.TrimPrefix(path, "/api/v1/desktop/")
	// Remove trailing slash
	action = strings.TrimRight(action, "/")

	switch action {
	case "screenshot":
		s.HandleDesktopScreenshot(w, r)
	case "click":
		s.HandleDesktopClick(w, r)
	case "type":
		s.HandleDesktopType(w, r)
	case "focus":
		s.HandleDesktopFocus(w, r)
	case "windows":
		s.HandleDesktopListWindows(w, r)
	case "find":
		s.HandleDesktopFind(w, r)
	default:
		w.WriteHeader(http.StatusNotFound)
		json.NewEncoder(w).Encode(map[string]string{
			"error": fmt.Sprintf("unknown desktop action: %s", action),
		})
	}
}
