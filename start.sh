#!/usr/bin/env bash
set -euo pipefail
umask 077

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${DM_INSTALL_DIR:-/opt/download-manager}"
VENV_PYTHON="${INSTALL_DIR}/venv/bin/python"
CONFIG_FILE="${DM_CONFIG:-/etc/download-manager/config.yml}"

if [ ! -f "${CONFIG_FILE}" ]; then
    echo "[start.sh] ERROR: Configuration file not found: ${CONFIG_FILE}" >&2
    exit 1
fi
if [ ! -x "${VENV_PYTHON}" ]; then
    echo "[start.sh] ERROR: Python environment is unavailable: ${VENV_PYTHON}" >&2
    exit 1
fi

cd "${APP_DIR}/backend"

# Upgrade bridge for installations whose legacy unit still owns both processes.
# New units set DM_ARIA2_EXTERNAL=1 and keep aria2 under its own supervisor.
if [ "${DM_ARIA2_EXTERNAL:-0}" = "1" ]; then
    exec "${VENV_PYTHON}" main.py
fi

"${APP_DIR}/start-aria2.sh" &
ARIA2_PID=$!
APP_PID=""
cleanup() {
    [ -n "${APP_PID}" ] && kill "${APP_PID}" 2>/dev/null || true
    kill "${ARIA2_PID}" 2>/dev/null || true
    wait "${ARIA2_PID}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
"${VENV_PYTHON}" main.py &
APP_PID=$!
wait "${APP_PID}"
