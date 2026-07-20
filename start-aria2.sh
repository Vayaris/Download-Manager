#!/usr/bin/env bash
set -euo pipefail
umask 077

INSTALL_DIR="${DM_INSTALL_DIR:-/opt/download-manager}"
CONFIG_FILE="${DM_CONFIG:-/etc/download-manager/config.yml}"
VENV_PYTHON="${INSTALL_DIR}/venv/bin/python"
STATE_DIR="${INSTALL_DIR}/config"
SESSION_FILE="${STATE_DIR}/aria2.session"
LOG_DIR="/var/log/download-manager"

if [ ! -f "${CONFIG_FILE}" ]; then
    echo "[start-aria2.sh] ERROR: Configuration file not found: ${CONFIG_FILE}" >&2
    exit 1
fi
if [ ! -x "${VENV_PYTHON}" ]; then
    echo "[start-aria2.sh] ERROR: Python environment is unavailable: ${VENV_PYTHON}" >&2
    exit 1
fi
if ! command -v aria2c >/dev/null 2>&1; then
    echo "[start-aria2.sh] ERROR: aria2c is not installed" >&2
    exit 1
fi

readarray -t SETTINGS < <("${VENV_PYTHON}" - "${CONFIG_FILE}" <<'PY'
import sys
import yaml

with open(sys.argv[1], encoding="utf-8") as handle:
    config = yaml.safe_load(handle) or {}
aria2 = config.get("aria2", {})
downloads = config.get("downloads", {})
print(int(aria2.get("rpc_port", 6800)))
print(str(aria2.get("rpc_secret", "download-manager-secret")))
print(str(downloads.get("default_destination", "/opt/download-manager/downloads")))
PY
)

ARIA2_PORT="${SETTINGS[0]:-6800}"
ARIA2_SECRET="${SETTINGS[1]:-download-manager-secret}"
DL_DIR="${SETTINGS[2]:-/opt/download-manager/downloads}"

install -d -m 700 "${STATE_DIR}" "${LOG_DIR}" "${DL_DIR}"
if [ ! -e "${SESSION_FILE}" ]; then
  install -m 600 /dev/null "${SESSION_FILE}"
else
  chmod 600 "${SESSION_FILE}"
fi

exec aria2c \
  --enable-rpc=true \
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
  --daemon=false \
  --input-file="${SESSION_FILE}" \
  --save-session="${SESSION_FILE}" \
  --save-session-interval=30 \
  --force-save=true \
  --log="${LOG_DIR}/aria2.log" \
  --log-level=warn
