# Phase 6: Polish - Implementation Plan

**Date:** 2026-05-09  
**Status:** In Progress  
**Goal:** Create production-ready installers, auto-updater, comprehensive documentation, and final polish.

---

## Overview

Phase 6 is the final polish phase before production release. This phase focuses on:
- Creating professional installers for all platforms
- Implementing automatic update mechanism
- Writing comprehensive documentation
- Adding performance benchmarks
- Final UI/UX polish

---

## Tasks

### Task 1: Create Windows MSI Installer (P0)
**Priority:** P0  
**Duration:** 2-3 days  
**Goal:** Create professional Windows installer using WiX Toolset

#### Steps
1. **Install WiX Toolset**
   ```powershell
   winget install WiXToolset.WiXToolset
   ```

2. **Create WiX configuration**
   - Directory: `supervisor/installers/windows/`
   - Files: `Product.wxs`, `Components.wxs`, `Directories.wxs`

3. **Configure installer features**
   - Install location: `C:\Program Files\AgentOS\`
   - Create desktop shortcut
   - Add to PATH (optional)
   - Create Start Menu entries
   - Register as Windows service (optional)

4. **Code signing (optional for MVP)**
   - Self-signed certificate for testing
   - Document CA signing process for production

5. **Build MSI**
   ```powershell
   candle Product.wxs
   light Product.wixobj -o AgentOS-Supervisor-v0.1.0.msi
   ```

#### Success Criteria
- [ ] MSI installs supervisor to correct location
- [ ] Desktop shortcut created
- [ ] Uninstall works cleanly via Add/Remove Programs
- [ ] File size < 50 MB

---

### Task 2: Create macOS DMG Installer (P0)
**Priority:** P0  
**Duration:** 2-3 days  
**Goal:** Create macOS app bundle with drag-and-drop DMG

#### Steps
1. **Create app bundle structure**
   - Directory: `supervisor/installers/macos/`
   - Structure: `AgentOS.app/Contents/MacOS/`, `AgentOS.app/Contents/Resources/`

2. **Build universal binary** (if supporting both Intel & Apple Silicon)
   ```bash
   GOOS=darwin GOARCH=amd64 go build -o supervisor-amd64
   GOOS=darwin GOARCH=arm64 go build -o supervisor-arm64
   lipo -create -output supervisor supervisor-amd64 supervisor-arm64
   ```

3. **Create Info.plist**
   - App metadata (name, version, bundle ID)
   - Icon file reference
   - Executable path

4. **Create DMG**
   ```bash
   create-dmg \
     --volname "AgentOS Installer" \
     --window-pos 200 120 \
     --window-size 600 400 \
     --icon-size 100 \
     --app-drop-link 450 185 \
     "AgentOS-v0.1.0.dmg" \
     "AgentOS.app/"
   ```

#### Success Criteria
- [ ] DMG opens with drag-and-drop interface
- [ ] App launches from Applications folder
- [ ] Code signed (or documented for production)
- [ ] Notarized (optional for MVP)

---

### Task 3: Create Linux AppImage (P1)
**Priority:** P1  
**Duration:** 2-3 days  
**Goal:** Create portable Linux AppImage

#### Steps
1. **Create AppDir structure**
   - Directory: `supervisor/installers/linux/AppDir/`
   - Structure: `usr/bin/`, `usr/share/applications/`, `usr/share/icons/`

2. **Create .desktop file**
   - Name: `agentos.desktop`
   - Categories: System;Utility;
   - Icon: agentos.png

3. **Download appimagetool**
   ```bash
   wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
   chmod +x appimagetool-x86_64.AppImage
   ```

4. **Build AppImage**
   ```bash
   ./appimagetool-x86_64.AppImage AppDir
   ```

5. **Test on multiple distros**
   - Ubuntu 22.04+
   - Fedora 38+
   - Debian 12+

#### Success Criteria
- [ ] AppImage runs without installation
- [ ] Works on major distros (Ubuntu, Fedora, Debian)
- [ ] File size < 30 MB

---

### Task 4: Implement Auto-Updater (P0)
**Priority:** P0  
**Duration:** 3-4 days  
**Goal:** Automatic background update checks and installation

#### Steps
1. **Design update mechanism**
   - Update server: S3 bucket or GitHub Releases
   - Manifest format: JSON with version, URL, checksums
   - Update channel: stable, beta, dev

2. **Create update manifest structure**
   ```json
   {
     "version": "0.1.1",
     "release_date": "2026-05-15",
     "download_url": {
       "windows": "https://.../AgentOS-v0.1.1-windows.msi",
       "macos": "https://.../AgentOS-v0.1.1-macos.dmg",
       "linux": "https://.../AgentOS-v0.1.1-linux.AppImage"
     },
     "checksums": {
       "sha256": "..."
     },
     "release_notes": "...",
     "mandatory": false
   }
   ```

3. **Implement update checker**
   - File: `supervisor/updater/updater.go`
   - Periodic check (every 24 hours)
   - Compare current version vs. latest
   - Notify user of available update

4. **Implement update downloader**
   - Download to temp location
   - Verify checksum
   - Stage update for installation

5. **Platform-specific installation**
   - Windows: Run MSI installer
   - macOS: Mount DMG, replace app
   - Linux: Replace AppImage

6. **Add CLI commands**
   ```bash
   ./supervisor.exe update check
   ./supervisor.exe update download
   ./supervisor.exe update install
   ```

#### Success Criteria
- [ ] Update check runs automatically
- [ ] Notifies user of available updates
- [ ] Can download and install updates
- [ ] Rollback on failure

---

### Task 5: Write User Documentation (P1)
**Priority:** P1  
**Duration:** 2-3 days  
**Goal:** Comprehensive user guide

#### Steps
1. **Create documentation structure**
   - Directory: `docs/user-guide/`
   - Files: `installation.md`, `quickstart.md`, `cli-reference.md`, `tui-guide.md`, `troubleshooting.md`

2. **Installation guide**
   - Windows installation
   - macOS installation
   - Linux installation
   - Verification steps

3. **Quick start guide**
   - First run
   - Basic configuration
   - Running first task
   - Using the TUI

4. **CLI reference**
   - Command structure
   - All subcommands with examples
   - Global flags

5. **TUI guide**
   - Navigation
   - Keyboard shortcuts
   - Views and panels

6. **Troubleshooting**
   - Common issues
   - Log locations
   - Debug mode

#### Success Criteria
- [ ] Complete user guide
- [ ] All commands documented
- [ ] Examples for common use cases

---

### Task 6: Write API Documentation (P1)
**Priority:** P1  
**Duration:** 2-3 days  
**Goal:** HTTP API reference documentation

#### Steps
1. **Create API docs structure**
   - Directory: `docs/api/`
   - Format: OpenAPI 3.0 + markdown

2. **Document all endpoints**
   - `/health`
   - `/status`
   - `/api/v1/python/*`
   - `/api/v1/agents/*`
   - `/api/v1/workers/*`

3. **Include examples**
   - Request/response for each endpoint
   - Error responses
   - Authentication (if applicable)

4. **Generate OpenAPI spec**
   - File: `docs/api/openapi.yaml`

#### Success Criteria
- [ ] All endpoints documented
- [ ] OpenAPI spec generated
- [ ] Example requests/responses

---

### Task 7: Write Deployment Guide (P1)
**Priority:** P1  
**Duration:** 2 days  
**Goal:** Guide for production deployment

#### Steps
1. **Create deployment docs**
   - Directory: `docs/deployment/`
   - Files: `overview.md`, `windows-service.md`, `systemd.md`, `docker.md`

2. **Windows service setup**
   - Using sc.exe
   - Using NSSM
   - Configuration

3. **Linux systemd setup**
   - Service file
   - Auto-start
   - Log rotation

4. **Docker deployment**
   - Dockerfile
   - docker-compose.yml
   - Volume mounts

#### Success Criteria
- [ ] Windows service guide
- [ ] Linux systemd guide
- [ ] Docker setup guide

---

### Task 8: Add Performance Benchmarks (P1)
**Priority:** P1  
**Duration:** 2-3 days  
**Goal:** Automated benchmarks and regression testing

#### Steps
1. **Create benchmark suite**
   - Directory: `benchmarks/`
   - Files: `gRPC_latency.go`, `http_api.go`, `memory_usage.go`

2. **gRPC latency benchmarks**
   - Measure RPC latency
   - Compare with target (< 5ms)
   - Report percentiles (p50, p95, p99)

3. **HTTP API benchmarks**
   - Load test endpoints
   - Measure throughput
   - Memory profiling

4. **Automated regression testing**
   - GitHub Actions workflow
   - Run on PR
   - Fail on regression

5. **Performance report generation**
   - Markdown report
   - Historical tracking
   - Visualization (optional)

#### Success Criteria
- [ ] gRPC latency benchmarks passing
- [ ] HTTP API benchmarks
- [ ] Automated CI/CD
- [ ] Regression detection

---

### Task 9: Final UI/UX Polish (P2)
**Priority:** P2  
**Duration:** 2-3 days  
**Goal:** Final polish for user experience

#### Steps
1. **Add icons and branding**
   - Icon for Windows (.ico)
   - Icon for macOS (.icns)
   - Icon for Linux (.png/.svg)
   - Assets: `assets/icons/`

2. **Improve error messages**
   - Review all error messages
   - Make user-friendly
   - Add suggestions for fixes
   - Include error codes

3. **Add progress indicators**
   - Installation progress
   - Update download progress
   - Task execution progress (TUI)

4. **Theme support (optional)**
   - Light/dark mode for TUI
   - Configurable color schemes

5. **Accessibility (optional)**
   - Screen reader support (TUI)
   - Keyboard navigation
   - High contrast mode

#### Success Criteria
- [ ] Professional icons for all platforms
- [ ] User-friendly error messages
- [ ] Progress indicators where appropriate

---

## Implementation Order

### Sprint 1 (Week 1)
1. ✅ Create Phase 6 plan (this document)
2. 🔄 Task 1: Windows MSI installer
3. 🔄 Task 2: macOS DMG installer

### Sprint 2 (Week 2)
4. Task 3: Linux AppImage
5. Task 4: Auto-updater (partial)

### Sprint 3 (Week 3)
6. Task 4: Auto-updater (complete)
7. Task 5: User documentation

### Sprint 4 (Week 4)
8. Task 6: API documentation
9. Task 7: Deployment guide
10. Task 8: Performance benchmarks

### Sprint 5 (Week 5)
11. Task 9: Final UI/UX polish
12. Final testing and release preparation

---

## Success Criteria

- [ ] Professional installers for all 3 platforms
- [ ] Auto-updater working
- [ ] Complete documentation (user, API, deployment)
- [ ] Performance benchmarks automated
- [ ] UI/UX polished and professional
- [ ] Ready for production release

---

## Notes

- **Code signing**: Can use self-signed certificates for MVP, document CA signing for production
- **Update server**: Can use GitHub Releases for MVP, migrate to dedicated infrastructure later
- **Documentation**: Host on GitHub Pages or similar for easy access
- **App Store**: Consider Mac App Store / Microsoft Store for v1.1
