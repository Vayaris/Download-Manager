#!/usr/bin/env bash
set -eo pipefail

# Read config values
CONFIG_FILE="${DM_CONFIG:-/etc/download-manager/config.yml}"
VENV_PYTHON="/opt/download-manager/venv/bin/python"

# Verify config file exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo "[start.sh] ERROR: Configuration file not found: $CONFIG_FILE" >&2
    exit 1
fi

# Verify aria2c is available
if ! command -v aria2c &> /dev/null; then
    echo "[start.sh] ERROR: aria2c is not installed or not in PATH" >&2
    exit 1
fi

# Use venv python (has PyYAML), fall back to system python3
PY="${VENV_PYTHON}"
[ -x "$PY" ] || PY="python3"

ARIA2_PORT=$("$PY" -c "
import yaml
with open('$CONFIG_FILE') as f:
    c = yaml.safe_load(f)
print(c.get('aria2', {}).get('rpc_port', 6800))
" 2>/dev/null || echo "6800")

ARIA2_SECRET=$("$PY" -c "
import yaml
with open('$CONFIG_FILE') as f:
    c = yaml.safe_load(f)
print(c.get('aria2', {}).get('rpc_secret', 'download-manager-secret'))
" 2>/dev/null || echo "download-manager-secret")

DL_DIR=$("$PY" -c "
import yaml
with open('$CONFIG_FILE') as f:
    c = yaml.safe_load(f)
print(c.get('downloads', {}).get('default_destination', '/opt/download-manager/downloads'))
" 2>/dev/null || echo "/opt/download-manager/downloads")

LOG_DIR="/var/log/download-manager"
mkdir -p "$LOG_DIR" "$DL_DIR"

# Stop any existing aria2 instance
pkill -f "aria2c.*rpc-listen-port=${ARIA2_PORT}" 2>/dev/null || true
sleep 1

# Start aria2c daemon
aria2c \
  --enable-rpc \
  --rpc-listen-port="${ARIA2_PORT}" \
  --rpc-secret="${ARIA2_SECRET}" \
  --rpc-listen-all=false \
  --dir="${DL_DIR}" \
  --max-concurrent-downloads=99 \
  --max-connection-per-server=5 \
  --split=5 \
  --min-split-size=10M \
  --continue=true \
  --auto-file-renaming=false \
  --allow-overwrite=true \
  --daemon=true \
  --log="${LOG_DIR}/aria2.log" \
  --log-level=warn

echo "[start.sh] aria2c started on RPC port ${ARIA2_PORT}"

# Start the FastAPI application
cd /opt/download-manager/backend
exec /opt/download-manager/venv/bin/python main.py
