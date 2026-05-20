#!/usr/bin/env bash
# Agent-OS Startup Script
# Starts the FastAPI HTTP server with minimal configuration.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Agent-OS Startup ==="

# 1. Check for .env file, copy from .env.example if missing
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo "[setup] Creating .env from .env.example"
        cp .env.example .env
        echo "[setup] Please edit .env to set your OPENAI_API_KEY and other settings."
    else
        echo "[warn] No .env or .env.example found. Ensure environment variables are set."
    fi
else
    echo "[ok] .env file found"
fi

# 2. Set SSL_CERT_FILE for Linux if not already set
if [ -z "$SSL_CERT_FILE" ]; then
    if [ -f /etc/pki/tls/certs/ca-bundle.crt ]; then
        export SSL_CERT_FILE=/etc/pki/tls/certs/ca-bundle.crt
        echo "[setup] SSL_CERT_FILE set to /etc/pki/tls/certs/ca-bundle.crt"
    elif [ -f /etc/ssl/certs/ca-certificates.crt ]; then
        export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
        echo "[setup] SSL_CERT_FILE set to /etc/ssl/certs/ca-certificates.crt"
    fi
else
    echo "[ok] SSL_CERT_FILE already set: $SSL_CERT_FILE"
fi

# 3. Install Python dependencies if needed
PYTHON=python3.12
if ! command -v "$PYTHON" &> /dev/null; then
    PYTHON=python3
fi

if ! "$PYTHON" -c "import fastapi" &> /dev/null; then
    echo "[setup] Installing Python dependencies..."
    "$PYTHON" -m pip install -r requirements.txt --quiet
else
    echo "[ok] Python dependencies already installed"
fi

# 4. Set default runtime mode to HTTP if not set
export AGENTOS_RUNTIME_MODE="${AGENTOS_RUNTIME_MODE:-http}"
export RUNTIME_MODE="${RUNTIME_MODE:-http}"

echo "[info] Runtime mode: $AGENTOS_RUNTIME_MODE"
echo "[info] Starting Agent-OS HTTP server on port 8000..."
echo ""

# 5. Start the server
exec "$PYTHON" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
