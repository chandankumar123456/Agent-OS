#!/usr/bin/env bash
# Agent-OS Startup Script
# Starts the unified kernel with optional HTTP adapter.

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

# 3. Find Python
PYTHON=python3.11
if ! command -v "$PYTHON" &> /dev/null; then
    PYTHON=python3
fi

# 4. Collect extra flags
EXTRA_FLAGS=""
if [ "${AGENTOS_HTTP:-}" = "1" ] || [ "${AGENTOS_HTTP:-}" = "true" ]; then
    EXTRA_FLAGS="--http"
    echo "[info] HTTP adapter enabled"
fi

echo "[info] Starting Agent-OS kernel..."
echo ""

# 5. Start the unified kernel
exec "$PYTHON" -m core $EXTRA_FLAGS "$@"
