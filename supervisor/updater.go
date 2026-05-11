package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"runtime"
	"strings"
	"time"
)

// UpdateManifest represents the remote update manifest
type UpdateManifest struct {
	Version     string `json:"version"`
	DownloadURL string `json:"download_url"`
	Checksum    string `json:"checksum"`
	ReleaseNotes string `json:"release_notes"`
	MinVersion  string `json:"min_version"`
	Force       bool   `json:"force"`
}

// UpdateInfo represents the current update status
type UpdateInfo struct {
	CurrentVersion string `json:"current_version"`
	LatestVersion  string `json:"latest_version"`
	Available      bool   `json:"available"`
	DownloadURL    string `json:"download_url,omitempty"`
	ReleaseNotes   string `json:"release_notes,omitempty"`
	Force          bool   `json:"force"`
}

// Updater handles update checking and application
type Updater struct {
	config    *Config
	client    *http.Client
	lastCheck time.Time
}

// NewUpdater creates a new updater
func NewUpdater(config *Config) *Updater {
	return &Updater{
		config: config,
		client: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

// CheckUpdate checks for available updates from the remote server
func (u *Updater) CheckUpdate() (*UpdateInfo, error) {
	if !u.config.Update.Enabled || u.config.Update.URL == "" {
		return &UpdateInfo{
			CurrentVersion: "0.1.0",
			LatestVersion:  "0.1.0",
			Available:      false,
		}, nil
	}

	manifestURL := fmt.Sprintf("%s/%s/%s/manifest.json",
		u.config.Update.URL,
		u.config.Update.Channel,
		runtime.GOOS,
	)

	resp, err := u.client.Get(manifestURL)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch update manifest: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == 404 {
		// No update available for this platform
		return &UpdateInfo{
			CurrentVersion: "0.1.0",
			LatestVersion:  "0.1.0",
			Available:      false,
		}, nil
	}

	if resp.StatusCode != 200 {
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

	u.lastCheck = time.Now()

	currentVersion := "0.1.0"
	available := manifest.Version != currentVersion

	return &UpdateInfo{
		CurrentVersion: currentVersion,
		LatestVersion:  manifest.Version,
		Available:      available,
		DownloadURL:    manifest.DownloadURL,
		ReleaseNotes:   manifest.ReleaseNotes,
		Force:          manifest.Force,
	}, nil
}

// DownloadUpdate downloads the update package to a temporary location
func (u *Updater) DownloadUpdate(url string) (string, error) {
	resp, err := u.client.Get(url)
	if err != nil {
		return "", fmt.Errorf("failed to download update: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return "", fmt.Errorf("download server returned status %d", resp.StatusCode)
	}

	// Create temporary file
	tmpFile, err := os.CreateTemp("", "agentos-update-*")
	if err != nil {
		return "", fmt.Errorf("failed to create temp file: %w", err)
	}
	defer tmpFile.Close()

	// Write downloaded content
	if _, err := io.Copy(tmpFile, resp.Body); err != nil {
		return "", fmt.Errorf("failed to write update: %w", err)
	}

	return tmpFile.Name(), nil
}

// VerifyUpdate verifies the downloaded update checksum using SHA-256
func (u *Updater) VerifyUpdate(filePath string, expectedChecksum string) error {
	if expectedChecksum == "" {
		log.Println("No expected checksum provided, skipping verification")
		return nil
	}

	// Read the downloaded file
	data, err := os.ReadFile(filePath)
	if err != nil {
		return fmt.Errorf("failed to read file for checksum: %w", err)
	}

	// Compute SHA-256 hash
	hash := sha256.Sum256(data)
	actualChecksum := hex.EncodeToString(hash[:])

	// Compare (case-insensitive)
	if !strings.EqualFold(actualChecksum, expectedChecksum) {
		return fmt.Errorf("checksum mismatch: expected %s, got %s", expectedChecksum, actualChecksum)
	}

	return nil
}

// ShouldAutoCheck returns true if enough time has passed since last check
func (u *Updater) ShouldAutoCheck() bool {
	if u.lastCheck.IsZero() {
		return true
	}

	interval, err := time.ParseDuration(u.config.Update.Interval)
	if err != nil {
		interval = 24 * time.Hour
	}

	return time.Since(u.lastCheck) > interval
}
