package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"time"

	"github.com/AgentOS/supervisor/logger"
)

// UpdateManifest represents the update manifest JSON structure
type UpdateManifest struct {
	Version      string            `json:"version"`
	ReleaseDate  string            `json:"release_date"`
	DownloadURLs map[string]string `json:"download_url"`
	Checksums    map[string]string `json:"checksums"`
	ReleaseNotes string            `json:"release_notes"`
	Mandatory    bool              `json:"mandatory"`
}

// Updater handles automatic updates
type Updater struct {
	logger         *logger.Logger
	currentVersion string
	updateURL      string
	channel        string // "stable", "beta", "dev"
}

// NewUpdater creates a new updater instance
func NewUpdater(log *logger.Logger, version, updateURL, channel string) *Updater {
	return &Updater{
		logger:         log,
		currentVersion: version,
		updateURL:      updateURL,
		channel:        channel,
	}
}

// CheckForUpdate checks if an update is available
func (u *Updater) CheckForUpdate() (*UpdateManifest, error) {
	u.logger.Info("Checking for updates")

	manifestURL := fmt.Sprintf("%s/manifest-%s.json", u.updateURL, u.channel)
	
	client := &http.Client{
		Timeout: 30 * time.Second,
	}
	
	resp, err := client.Get(manifestURL)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch update manifest: %w", err)
	}
	defer resp.Body.Close()
	
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("update server returned status %d", resp.StatusCode)
	}
	
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read manifest: %w", err)
	}
	
	var manifest UpdateManifest
	if err := json.Unmarshal(body, &manifest); err != nil {
		return nil, fmt.Errorf("failed to parse manifest: %w", err)
	}
	
	// Check if version is newer
	if !u.isNewerVersion(manifest.Version) {
		u.logger.Info("No updates available")
		return nil, nil
	}
	
	u.logger.Info("Update available")
	
	return &manifest, nil
}

// isNewerVersion compares version strings (simple semver comparison)
func (u *Updater) isNewerVersion(newVersion string) bool {
	// Simple version comparison: "0.1.0" < "0.2.0" < "1.0.0"
	return newVersion > u.currentVersion
}

// DownloadUpdate downloads the update package
func (u *Updater) DownloadUpdate(manifest *UpdateManifest) (string, error) {
	u.logger.Info("Downloading update")
	
	// Get platform-specific URL
	platformKey := u.getPlatformKey()
	url, ok := manifest.DownloadURLs[platformKey]
	if !ok {
		return "", fmt.Errorf("no download URL for platform: %s", platformKey)
	}
	
	// Create temp directory
	tempDir, err := os.MkdirTemp("", "agentos-update-*")
	if err != nil {
		return "", fmt.Errorf("failed to create temp directory: %w", err)
	}
	
	// Download file
	filename := filepath.Base(url)
	if filename == "" {
		filename = fmt.Sprintf("agentos-update-%s", manifest.Version)
	}
	
	filepath := filepath.Join(tempDir, filename)
	
	client := &http.Client{
		Timeout: 5 * time.Minute,
	}
	
	resp, err := client.Get(url)
	if err != nil {
		return "", fmt.Errorf("failed to download update: %w", err)
	}
	defer resp.Body.Close()
	
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("download server returned status %d", resp.StatusCode)
	}
	
	file, err := os.Create(filepath)
	if err != nil {
		return "", fmt.Errorf("failed to create file: %w", err)
	}
	defer file.Close()
	
	written, err := io.Copy(file, resp.Body)
	if err != nil {
		return "", fmt.Errorf("failed to write update file: %w", err)
	}
	
	u.logger.Info(fmt.Sprintf("Update downloaded: %d bytes", written))
	
	// Verify checksum (optional)
	if checksum, ok := manifest.Checksums[platformKey]; ok && checksum != "" {
		// TODO: Implement checksum verification
		u.logger.Info("Checksum verification skipped")
	}
	
	return filepath, nil
}

// getPlatformKey returns the platform key for download URLs
func (u *Updater) getPlatformKey() string {
	os := runtime.GOOS
	
	switch os {
	case "windows":
		return "windows"
	case "darwin":
		return "macos"
	case "linux":
		return "linux"
	default:
		return os
	}
}

// UpdateState represents the current update state
type UpdateState struct {
	CurrentVersion string    `json:"current_version"`
	LastCheck      time.Time `json:"last_check"`
	LastVersion    string    `json:"last_version"`
	UpdateReady    bool      `json:"update_ready"`
	UpdatePath     string    `json:"update_path,omitempty"`
}

// GetState returns the current update state
func (u *Updater) GetState() *UpdateState {
	// TODO: Load from config file
	return &UpdateState{
		CurrentVersion: u.currentVersion,
		LastCheck:      time.Time{},
		LastVersion:    "",
		UpdateReady:    false,
	}
}

// SaveState saves the update state
func (u *Updater) SaveState(state *UpdateState) error {
	// TODO: Save to config file
	return nil
}
