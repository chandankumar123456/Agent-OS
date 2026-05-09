# AgentOS Deployment Guide

Guide for deploying AgentOS in production environments.

---

## Table of Contents

1. [Overview](#overview)
2. [Windows Service Deployment](#windows-service-deployment)
3. [Linux systemd Deployment](#linux-systemd-deployment)
4. [Docker Deployment](#docker-deployment)
5. [Production Configuration](#production-configuration)
6. [Monitoring & Alerting](#monitoring--alerting)
7. [Backup & Recovery](#backup--recovery)

---

## Overview

AgentOS can be deployed in several ways depending on your environment:

| Method | Best For | Complexity |
|--------|----------|------------|
| Windows Service | Windows servers | Medium |
| systemd | Linux servers | Medium |
| Docker | Containerized environments | Low |
| Kubernetes | Large-scale deployments | High |

---

## Windows Service Deployment

### Method 1: Using sc.exe (Built-in)

1. Install AgentOS using the MSI installer

2. Create the service:
```powershell
sc.exe create AgentOS binPath= "\"C:\Program Files\AgentOS\bin\supervisor.exe\" -data-dir \"C:\ProgramData\AgentOS\"" start= auto
```

3. Configure service:
```powershell
sc.exe config AgentOS displayName= "AgentOS Supervisor"
sc.exe config AgentOS description= "AgentOS local-native runtime supervisor"
```

4. Start the service:
```powershell
sc.exe start AgentOS
```

5. Check status:
```powershell
sc.exe query AgentOS
```

### Method 2: Using NSSM (Recommended)

NSSM provides better logging and restart capabilities.

1. Download NSSM from https://nssm.cc/

2. Install the service:
```powershell
nssm.exe install AgentOS
```

3. Configure in the GUI:
   - Path: `C:\Program Files\AgentOS\bin\supervisor.exe`
   - Startup directory: `C:\Program Files\AgentOS\bin`
   - Arguments: `-data-dir "C:\ProgramData\AgentOS" -log-level info`

4. Or via command line:
```powershell
nssm.exe set AgentOS Application "C:\Program Files\AgentOS\bin\supervisor.exe"
nssm.exe set AgentOS AppDirectory "C:\Program Files\AgentOS\bin"
nssm.exe set AgentOS AppParameters "-data-dir C:\ProgramData\AgentOS -log-level info"
nssm.exe set AgentOS DisplayName "AgentOS Supervisor"
nssm.exe set AgentOS Description "AgentOS local-native runtime supervisor"
```

5. Configure logging:
```powershell
nssm.exe set AgentOS AppStdout "C:\ProgramData\AgentOS\logs\supervisor.log"
nssm.exe set AgentOS AppStderr "C:\ProgramData\AgentOS\logs\supervisor-error.log"
```

6. Configure auto-restart:
```powershell
nssm.exe set AgentOS AppExit Default Restart
nssm.exe set AgentOS AppRestartDelay 5000
```

7. Start the service:
```powershell
nssm.exe start AgentOS
```

### Service Management

```powershell
# Start
sc.exe start AgentOS

# Stop
sc.exe stop AgentOS

# Restart
sc.exe stop AgentOS
sc.exe start AgentOS

# Remove service
sc.exe delete AgentOS
```

---

## Linux systemd Deployment

### Create systemd Service File

1. Create the service file:
```bash
sudo nano /etc/systemd/system/agentos.service
```

2. Add the following content:
```ini
[Unit]
Description=AgentOS Supervisor
Documentation=https://docs.agentos.dev
After=network.target

[Service]
Type=simple
User=agentos
Group=agentos

WorkingDirectory=/opt/agentos

ExecStart=/opt/agentos/supervisor \
    -host 127.0.0.1 \
    -port 8080 \
    -data-dir /var/lib/agentos \
    -log-level info

Restart=always
RestartSec=5

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/agentos /var/log/agentos

# Resource limits
LimitNOFILE=65536
LimitNPROC=4096

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=agentos

[Install]
WantedBy=multi-user.target
```

3. Create user and directories:
```bash
# Create user
sudo useradd -r -s /bin/false agentos

# Create directories
sudo mkdir -p /opt/agentos /var/lib/agentos /var/log/agentos

# Copy binary
sudo cp /path/to/supervisor /opt/agentos/
sudo chmod +x /opt/agentos/supervisor

# Set ownership
sudo chown -R agentos:agentos /opt/agentos /var/lib/agentos /var/log/agentos
```

4. Reload systemd and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable agentos
sudo systemctl start agentos
```

5. Check status:
```bash
sudo systemctl status agentos
```

### Log Rotation

Create log rotation config:

```bash
sudo nano /etc/logrotate.d/agentos
```

Add:
```
/var/log/agentos/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0644 agentos agentos
    sharedscripts
    postrotate
        systemctl reload agentos
    endscript
}
```

### Service Management

```bash
# Start
sudo systemctl start agentos

# Stop
sudo systemctl stop agentos

# Restart
sudo systemctl restart agentos

# View logs
sudo journalctl -u agentos -f

# View recent logs
sudo journalctl -u agentos --since "1 hour ago"
```

---

## Docker Deployment

### Dockerfile

Create `Dockerfile`:

```dockerfile
# Build stage
FROM golang:1.21-alpine AS builder

WORKDIR /build
COPY supervisor/ .
RUN go build -o supervisor .

# Runtime stage
FROM alpine:latest

RUN apk add --no-cache ca-certificates

WORKDIR /app

# Copy binary
COPY --from=builder /build/supervisor /app/

# Create data directory
RUN mkdir -p /data && chmod 755 /data

# Expose ports
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:8080/health || exit 1

# Run supervisor
ENTRYPOINT ["/app/supervisor"]
CMD ["-data-dir", "/data", "-host", "0.0.0.0", "-port", "8080"]
```

### Build and Run

```bash
# Build image
docker build -t agentos:latest .

# Run container
docker run -d \
  --name agentos \
  -p 8080:8080 \
  -v agentos-data:/data \
  --restart unless-stopped \
  agentos:latest
```

### Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  agentos:
    build: .
    image: agentos:latest
    container_name: agentos
    restart: unless-stopped
    ports:
      - "8080:8080"
    volumes:
      - agentos-data:/data
      - ./config:/config:ro
    environment:
      - AGENTOS_LOG_LEVEL=info
      - AGENTOS_DATA_DIR=/data
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

volumes:
  agentos-data:
```

Run with Docker Compose:
```bash
docker-compose up -d
```

### Docker Swarm

Deploy to Docker Swarm:

```bash
# Initialize swarm (if not already)
docker swarm init

# Deploy stack
docker stack deploy -c docker-compose.yml agentos

# Scale service
docker service scale agentos_agentos=3
```

---

## Production Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AGENTOS_HOST` | Bind host | `127.0.0.1` |
| `AGENTOS_PORT` | HTTP port | `8080` |
| `AGENTOS_LOG_LEVEL` | Log level | `info` |
| `AGENTOS_DATA_DIR` | Data directory | `~/.agentos` |
| `AGENTOS_CONFIG_PATH` | Config file path | `~/.agentos/config/default.yaml` |

### Security Hardening

#### File Permissions

```bash
# Linux/macOS
chmod 750 /opt/agentos
chmod 755 /opt/agentos/supervisor
chmod 700 /var/lib/agentos
chmod 755 /var/log/agentos
```

#### Firewall Rules

```bash
# Linux (ufw)
sudo ufw allow 8080/tcp
sudo ufw deny 8080/tcp from any to any
sudo ufw allow from 10.0.0.0/8 to any port 8080

# Windows (PowerShell)
New-NetFirewallRule -DisplayName "AgentOS" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow
```

#### TLS/SSL

Use a reverse proxy (nginx, Caddy, Traefik) for TLS termination:

**nginx example:**
```nginx
server {
    listen 443 ssl;
    server_name agentos.example.com;

    ssl_certificate /etc/ssl/certs/agentos.crt;
    ssl_certificate_key /etc/ssl/private/agentos.key;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

---

## Monitoring & Alerting

### Prometheus Metrics

AgentOS exposes Prometheus metrics at `/health/metrics`:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'agentos'
    static_configs:
      - targets: ['localhost:8080']
    metrics_path: /health/metrics
```

### Grafana Dashboard

Create a Grafana dashboard with panels for:
- Active sessions
- Request rate
- Error rate
- Response latency
- Worker pool status

### Health Checks

**HTTP Health Check:**
```bash
curl -f http://localhost:8080/health || exit 1
```

**TCP Health Check:**
```bash
timeout 3 bash -c 'cat < /dev/null > /dev/tcp/localhost/8080' || exit 1
```

### Alerting Rules

**Prometheus Alerting Rules:**
```yaml
groups:
  - name: agentos
    rules:
      - alert: AgentOSDown
        expr: up{job="agentos"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "AgentOS is down"
          
      - alert: AgentOSHighErrorRate
        expr: rate(agentos_requests_total{status="error"}[5m]) > 0.1
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "AgentOS high error rate"
```

---

## Backup & Recovery

### Database Backup

The SQLite database is located at `{data_dir}/supervisor.db`.

**Backup:**
```bash
# While running (online backup)
sqlite3 /var/lib/agentos/supervisor.db ".backup '/backup/agentos-$(date +%Y%m%d).db'"

# Or copy file (when stopped)
cp /var/lib/agentos/supervisor.db /backup/agentos-$(date +%Y%m%d).db
```

**Automated Backup (Linux):**
```bash
# Add to crontab
0 2 * * * sqlite3 /var/lib/agentos/supervisor.db ".backup '/backup/agentos-$(date +\%Y\%m\%d).db'" && find /backup -name "agentos-*.db" -mtime +30 -delete
```

### Recovery

1. Stop AgentOS:
```bash
sudo systemctl stop agentos
```

2. Restore from backup:
```bash
cp /backup/agentos-20260509.db /var/lib/agentos/supervisor.db
sudo chown agentos:agentos /var/lib/agentos/supervisor.db
```

3. Start AgentOS:
```bash
sudo systemctl start agentos
```

### Configuration Backup

```bash
# Backup config
tar -czf agentos-config-$(date +%Y%m%d).tar.gz ~/.agentos/config/

# Restore config
tar -xzf agentos-config-20260509.tar.gz -C ~/
```

---

## Troubleshooting Production Issues

### High Memory Usage

1. Check worker pool size:
```bash
curl http://localhost:8080/api/v1/workers/status
```

2. Adjust worker limits in config

3. Monitor with:
```bash
ps aux | grep supervisor
```

### Slow Response Times

1. Check metrics:
```bash
curl http://localhost:8080/api/v1/workers/metrics
```

2. Scale worker pool if needed:
```bash
curl -X POST http://localhost:8080/api/v1/workers/scale -d '{"size": 20}'
```

3. Check database size:
```bash
ls -lh /var/lib/agentos/supervisor.db
```

### Database Corruption

If the SQLite database becomes corrupted:

1. Stop AgentOS
2. Backup the corrupted database
3. Attempt repair:
```bash
sqlite3 /var/lib/agentos/supervisor.db ".recover" | sqlite3 /var/lib/agentos/supervisor-recovered.db
```
4. Replace if successful
5. If unsuccessful, restore from backup

---

## Next Steps

- Configure [High Availability](high-availability.md)
- Set up [Monitoring Stack](monitoring.md)
- Read [Security Best Practices](security.md)

---

**Version:** 0.1.0  
**Last Updated:** 2026-05-09
