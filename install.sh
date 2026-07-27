#!/usr/bin/env bash
# ============================================================
#  Download Manager — Installation Script
#  Compatible: Ubuntu 20.04+, Debian 11+ (VM / LXC Proxmox)
# ============================================================
# NOTE: No "set -eo pipefail" — we handle errors explicitly
# so the script never exits silently mid-way.

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; NC='\033[0m'; BOLD='\033[1m'

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERR]${NC}   $*"; }
die()     { error "$*"; exit 1; }

# ---- Root check ----
[ "$(id -u)" -eq 0 ] || die "This script must be run as root. Use: sudo bash install.sh"

# ---- Banner ----
echo ""
echo -e "${BOLD}╔═══════════════════════════════════════╗${NC}"
echo -e "${BOLD}║       Download Manager — Install      ║${NC}"
echo -e "${BOLD}╚═══════════════════════════════════════╝${NC}"
echo ""

# ---- Paths ----
INSTALL_DIR="/opt/download-manager"
CONFIG_DIR="/etc/download-manager"
LOG_DIR="/var/log/download-manager"
STATE_DIR="/var/lib/download-manager"
BACKUP_ROOT="/var/backups/download-manager"
REPOSITORY_DIR="${STATE_DIR}/repository.git"
RELEASES_DIR="${INSTALL_DIR}/releases"
VENVS_DIR="${INSTALL_DIR}/venvs"
UPGRADE_MODE=0
[ "${1:-}" = "--upgrade" ] && UPGRADE_MODE=1
CLONED_TEMP=""

# ---- Detect execution context (local clone vs bash <(curl ...)) ----
_raw_source="${BASH_SOURCE[0]:-}"
if [[ "$_raw_source" == /dev/fd/* ]] || [[ "$_raw_source" == /proc/* ]] || [ -z "$_raw_source" ]; then
    SCRIPT_DIR=""
else
    SCRIPT_DIR="$(cd "$(dirname "$_raw_source")" 2>/dev/null && pwd)" || SCRIPT_DIR=""
fi

# ---- Clone from GitHub if needed ----
if [ -z "${SCRIPT_DIR}" ] || [ ! -f "${SCRIPT_DIR}/requirements.txt" ]; then
    info "Downloading project from GitHub..."
    apt-get update -qq 2>/dev/null || true
    apt-get install -y -qq git 2>/dev/null || apt-get install -y git || die "Failed to install git"
    CLONED_TEMP="$(mktemp -d)"
    git clone --depth 1 https://github.com/Vayaris/Download-Manager.git "${CLONED_TEMP}/download-manager" \
        || die "Failed to clone repository from GitHub"
    SCRIPT_DIR="${CLONED_TEMP}/download-manager"
    success "Project downloaded"
    echo ""
fi

# ---- Port selection ----
DEFAULT_PORT=40320
if [ "${UPGRADE_MODE}" -eq 1 ] && [ -f "${CONFIG_DIR}/config.yml" ]; then
    PORT=$(awk '/^server:/{inside=1; next} inside && /^[^[:space:]]/{inside=0} inside && /^[[:space:]]+port:/{print $2; exit}' "${CONFIG_DIR}/config.yml")
    PORT="${PORT:-$DEFAULT_PORT}"
    info "Upgrade mode: preserving the configured port ${PORT}"
else
    read -rp "Which port should the web interface listen on? [${DEFAULT_PORT}] : " INPUT_PORT
    PORT="${INPUT_PORT:-$DEFAULT_PORT}"
fi

if ! echo "$PORT" | grep -qE '^[0-9]+$' || [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
    warn "Invalid port, using default: ${DEFAULT_PORT}"
    PORT=$DEFAULT_PORT
fi

info "Selected port: ${PORT}"
echo ""

# ---- System dependencies ----
info "Updating package list..."
apt-get update -q || warn "apt-get update had warnings (continuing)"

info "Installing system dependencies (this may take a minute)..."
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    gcc \
    aria2 \
    cifs-utils \
    curl \
    wget \
    git \
    ca-certificates \
    2>&1 | grep -v "^Reading\|^Building\|^Fetching\|^Selecting\|^Preparing\|^Unpacking\|^Setting up\|^Processing" || true

# Verify critical tools installed
if ! command -v python3 >/dev/null 2>&1; then
    die "python3 could not be installed. Check your package manager."
fi
if ! command -v aria2c >/dev/null 2>&1; then
    die "aria2c could not be installed. Check your package manager."
fi

# Check Python version
PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
if [ "$PYTHON_MAJOR" -lt 3 ] || ( [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ] ); then
    die "Python 3.10+ required. Found: ${PYTHON_VERSION}"
fi
success "Python ${PYTHON_VERSION} detected"
success "aria2c $(aria2c --version | head -1 | awk '{print $3}') installed"

# Check port usage (warning only)
if command -v ss >/dev/null 2>&1; then
    if ss -tlnp 2>/dev/null | grep -q ":${PORT} "; then
        warn "Port ${PORT} is already in use. The service may fail to start."
    fi
fi

# ---- Create directories ----
info "Creating directory structure..."
mkdir -p "${INSTALL_DIR}"/{downloads,config,releases,venvs}
mkdir -p "${CONFIG_DIR}"
mkdir -p "${LOG_DIR}"
mkdir -p "${STATE_DIR}" "${BACKUP_ROOT}"
chmod 700 "${STATE_DIR}" "${BACKUP_ROOT}"

# ---- Prepare immutable release ----
VERSION=$(tr -d '[:space:]' < "${SCRIPT_DIR}/VERSION")
[ -n "${VERSION}" ] || die "VERSION is empty"
RELEASE_DIR="${RELEASES_DIR}/v${VERSION}"
RELEASE_STAGING="${RELEASES_DIR}/.v${VERSION}.installer-staging"
info "Preparing release v${VERSION}..."
rm -rf "${RELEASE_STAGING}"
mkdir -p "${RELEASE_STAGING}"
for path in backend frontend deploy requirements.txt start.sh start-aria2.sh VERSION; do
    [ -e "${SCRIPT_DIR}/${path}" ] || die "Release source is missing ${path}"
    cp -a "${SCRIPT_DIR}/${path}" "${RELEASE_STAGING}/"
done
chmod 755 "${RELEASE_STAGING}/start.sh" "${RELEASE_STAGING}/start-aria2.sh"
rm -rf "${RELEASE_DIR}"
mv "${RELEASE_STAGING}" "${RELEASE_DIR}"
success "Release v${VERSION} prepared"

# ---- Generate aria2 secret ----
ARIA2_SECRET=$(tr -dc 'a-zA-Z0-9' < /dev/urandom | head -c 32)

# ---- Config file ----
if [ -f "${CONFIG_DIR}/config.yml" ]; then
    info "Existing configuration detected and preserved."
    if [ "${UPGRADE_MODE}" -ne 1 ]; then
        sed -i "s/^\(\s*port:\s*\).*/\1${PORT}/" "${CONFIG_DIR}/config.yml"
    fi
    if ! grep -q "webhooks:" "${CONFIG_DIR}/config.yml" 2>/dev/null; then
        cat >> "${CONFIG_DIR}/config.yml" <<EOF

webhooks:
  enabled: false
  url: ""
  format: "generic"
  events:
    - "download_complete"
    - "download_failed"
    - "package_complete"
EOF
        info "Webhooks section added to configuration"
    fi
else
    info "Creating configuration file..."
    cat > "${CONFIG_DIR}/config.yml" <<EOF
server:
  host: "0.0.0.0"
  port: ${PORT}
  cors_origins: []
  trusted_proxies: []

alldebrid:
  api_key: ""
  enabled: false

downloads:
  simultaneous: 3
  download_segments: 1
  speed_limit: 0
  max_retries: 3
  retry_delay_seconds: 5
  skip_nfo_files: true
  stalled_timeout_hours: 3
  default_destination: "${INSTALL_DIR}/downloads"
  allowed_paths:
    - "/mnt"
    - "${INSTALL_DIR}/downloads"

auth:
  jwt_secret: ""

aria2:
  rpc_port: 6800
  rpc_secret: "${ARIA2_SECRET}"

webhooks:
  enabled: false
  url: ""
  format: "generic"
  events:
    - "download_complete"
    - "download_failed"
    - "package_complete"

plex:
  enabled: false
  url: "http://127.0.0.1:32400"
  token: ""
  last_refreshes: {}
  favorite_keys: []
  auto_refresh_enabled: false
  auto_refresh_enabled_at: null
  auto_refreshes: {}
  auto_refresh_last_result: null

jellyfin:
  enabled: false
  url: "http://127.0.0.1:8096"
  token: ""
  last_refreshes: {}
  favorite_keys: []
  auto_refresh_enabled: false
  auto_refresh_enabled_at: null
  auto_refreshes: {}
  auto_refresh_last_result: null
  path_mappings: []

media:
  active: "plex"

youtube:
  direct_enabled: false
  max_concurrent: 2
  speed_limit: 0
EOF
    success "Configuration created: ${CONFIG_DIR}/config.yml"
fi

# ---- Isolated Python environment ----
TARGET_VENV="${VENVS_DIR}/v${VERSION}"
rm -rf "${TARGET_VENV}"
info "Creating isolated Python environment for v${VERSION}..."
if ! python3 -m venv "${TARGET_VENV}"; then
        warn "python3 -m venv failed, trying python3-venv package..."
        apt-get install -y python3-venv python3-full 2>/dev/null || true
        if ! python3 -m venv "${TARGET_VENV}"; then
            die "Failed to create Python virtualenv. Try: apt-get install python3-venv"
        fi
fi

info "Upgrading pip..."
"${TARGET_VENV}/bin/pip" install --upgrade pip --quiet || true

info "Installing Python dependencies (this may take several minutes due to native compilation)..."
if ! "${TARGET_VENV}/bin/pip" install -r "${RELEASE_DIR}/requirements.txt"; then
    error "pip install failed. Trying with verbose output..."
    "${TARGET_VENV}/bin/pip" install -r "${RELEASE_DIR}/requirements.txt" --no-cache-dir \
        || die "Failed to install Python dependencies. Check the errors above."
fi
"${TARGET_VENV}/bin/python" -m compileall -q "${RELEASE_DIR}/backend" || die "Backend compilation failed"
success "Python dependencies installed"

# Existing installations may have been created before private data modes were
# enforced. Tighten them without changing ownership or touching media paths.
chmod 700 "${CONFIG_DIR}" "${INSTALL_DIR}/config" /var/lib/download-manager /var/backups/download-manager 2>/dev/null || true
chmod 600 "${CONFIG_DIR}/config.yml" "${INSTALL_DIR}/config/downloads.db" 2>/dev/null || true

# ---- Private bare repository for future updates ----
if [ ! -d "${REPOSITORY_DIR}" ]; then
    info "Creating private update repository..."
    git clone --mirror https://github.com/Vayaris/Download-Manager.git "${REPOSITORY_DIR}" >/dev/null 2>&1 \
        || die "Could not create the update repository"
else
    git --git-dir="${REPOSITORY_DIR}" fetch --force --prune origin '+refs/tags/*:refs/tags/*' >/dev/null 2>&1 \
        || warn "Could not refresh the update repository"
fi
chmod 700 "${REPOSITORY_DIR}"

# ---- Backup and atomic runtime switch ----
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
INSTALL_BACKUP="${BACKUP_ROOT}/installer-v${VERSION}-${STAMP}"
mkdir -m 700 "${INSTALL_BACKUP}" || die "Could not create installer backup"
[ -f "${CONFIG_DIR}/config.yml" ] && cp -a "${CONFIG_DIR}/config.yml" "${INSTALL_BACKUP}/config.yml"
if [ -f "${INSTALL_DIR}/config/downloads.db" ]; then
    BACKUP_DB="${INSTALL_BACKUP}/downloads.db" "${TARGET_VENV}/bin/python" - <<'PY' || die "SQLite backup failed"
import os, sqlite3
source = sqlite3.connect('/opt/download-manager/config/downloads.db')
target = sqlite3.connect(os.environ['BACKUP_DB'])
with target:
    source.backup(target)
source.close(); target.close(); os.chmod(os.environ['BACKUP_DB'], 0o600)
PY
fi
mkdir -m 700 "${INSTALL_BACKUP}/systemd"
for unit in download-manager.service download-manager-aria2.service; do
    [ -f "/etc/systemd/system/${unit}" ] && cp -a "/etc/systemd/system/${unit}" "${INSTALL_BACKUP}/systemd/${unit}"
done

PREVIOUS_CURRENT=""
[ -L "${INSTALL_DIR}/current" ] && PREVIOUS_CURRENT=$(readlink -f "${INSTALL_DIR}/current")
PREVIOUS_VENV=""
if [ -L "${INSTALL_DIR}/venv" ]; then
    PREVIOUS_VENV=$(readlink -f "${INSTALL_DIR}/venv")
elif [ -d "${INSTALL_DIR}/venv" ]; then
    PREVIOUS_VENV="${VENVS_DIR}/legacy-${STAMP}"
fi

if command -v systemctl >/dev/null 2>&1 && systemctl --version >/dev/null 2>&1; then
    HAVE_SYSTEMD=1
    systemctl stop download-manager.service download-manager-aria2.service 2>/dev/null || true
else
    HAVE_SYSTEMD=0
fi
if [ -d "${INSTALL_DIR}/venv" ] && [ ! -L "${INSTALL_DIR}/venv" ]; then
    mv "${INSTALL_DIR}/venv" "${PREVIOUS_VENV}" || die "Could not preserve the previous virtualenv"
fi
ln -sfn "${RELEASE_DIR}" "${INSTALL_DIR}/.current-new"
mv -Tf "${INSTALL_DIR}/.current-new" "${INSTALL_DIR}/current"
ln -sfn "${TARGET_VENV}" "${INSTALL_DIR}/.venv-new"
mv -Tf "${INSTALL_DIR}/.venv-new" "${INSTALL_DIR}/venv"

if [ "${HAVE_SYSTEMD}" -eq 1 ]; then
    info "Installing Download Manager systemd units..."
    cp "${RELEASE_DIR}/deploy/systemd/download-manager.service" /etc/systemd/system/download-manager.service
    cp "${RELEASE_DIR}/deploy/systemd/download-manager-aria2.service" /etc/systemd/system/download-manager-aria2.service
    chmod 644 /etc/systemd/system/download-manager.service /etc/systemd/system/download-manager-aria2.service
    systemd-analyze verify /etc/systemd/system/download-manager.service /etc/systemd/system/download-manager-aria2.service \
        || die "The Download Manager systemd units are invalid"
    systemctl daemon-reload
    systemctl enable download-manager-aria2.service download-manager.service >/dev/null 2>&1 || true
fi

restore_previous_installation() {
    error "The new runtime failed its health check; restoring the previous installation."
    systemctl stop download-manager.service download-manager-aria2.service 2>/dev/null || true
    if [ -n "${PREVIOUS_CURRENT}" ]; then
        ln -sfn "${PREVIOUS_CURRENT}" "${INSTALL_DIR}/.current-rollback"
        mv -Tf "${INSTALL_DIR}/.current-rollback" "${INSTALL_DIR}/current"
    else
        rm -f "${INSTALL_DIR}/current"
    fi
    if [ -n "${PREVIOUS_VENV}" ]; then
        ln -sfn "${PREVIOUS_VENV}" "${INSTALL_DIR}/.venv-rollback"
        mv -Tf "${INSTALL_DIR}/.venv-rollback" "${INSTALL_DIR}/venv"
    fi
    [ -f "${INSTALL_BACKUP}/config.yml" ] && cp -a "${INSTALL_BACKUP}/config.yml" "${CONFIG_DIR}/config.yml"
    if [ -f "${INSTALL_BACKUP}/downloads.db" ]; then
        rm -f "${INSTALL_DIR}/config/downloads.db-wal" "${INSTALL_DIR}/config/downloads.db-shm"
        cp -a "${INSTALL_BACKUP}/downloads.db" "${INSTALL_DIR}/config/downloads.db"
    fi
    for unit in download-manager.service download-manager-aria2.service; do
        if [ -f "${INSTALL_BACKUP}/systemd/${unit}" ]; then
            cp -a "${INSTALL_BACKUP}/systemd/${unit}" "/etc/systemd/system/${unit}"
        else
            rm -f "/etc/systemd/system/${unit}"
        fi
    done
    systemctl daemon-reload 2>/dev/null || true
    systemctl restart download-manager.service 2>/dev/null || true
    die "Upgrade rolled back. See ${INSTALL_BACKUP} and journalctl -u download-manager -n 100"
}

# ---- Start service ----
if [ "${HAVE_SYSTEMD:-0}" -eq 1 ]; then
    info "Starting Download Manager service..."
    systemctl reset-failed download-manager download-manager-aria2 2>/dev/null || true
    START_OK=0
    if systemctl restart download-manager-aria2.service download-manager.service; then
        # Wait up to 10 seconds for service to become active
        for i in 1 2 3 4 5 6 7 8 9 10; do
            sleep 1
            if systemctl is-active --quiet download-manager \
                && systemctl is-active --quiet download-manager-aria2 \
                && curl -fsS --max-time 2 "http://127.0.0.1:${PORT}/api/auth/status" >/dev/null; then
                success "Service started successfully"
                START_OK=1
                break
            fi
            if [ "$i" -eq 10 ]; then
                warn "Service did not start within 10s."
            fi
        done
    else
        warn "Failed to start Download Manager services."
    fi
    [ "${START_OK}" -eq 1 ] || restore_previous_installation
else
    info "Starting Download Manager manually..."
    nohup "${INSTALL_DIR}/current/start-aria2.sh" >> "${LOG_DIR}/aria2-console.log" 2>&1 &
    DM_ARIA2_EXTERNAL=1 nohup "${INSTALL_DIR}/current/start.sh" >> "${LOG_DIR}/download-manager.log" 2>&1 &
    sleep 3
    warn "systemd not available — service started in background (PID: $!). It will NOT restart automatically."
fi

# ---- Cleanup temp clone ----
if [ -n "${CLONED_TEMP}" ] && [ -d "${CLONED_TEMP}" ]; then
    rm -rf "${CLONED_TEMP}"
fi

# ---- Summary ----
SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$SERVER_IP" ] && SERVER_IP="<your-server-ip>"

echo ""
echo -e "${BOLD}╔═══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║         Installation completed successfully!      ║${NC}"
echo -e "${BOLD}╚═══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}Access the web interface:${NC}"
echo -e "    ${BOLD}${GREEN}http://${SERVER_IP}:${PORT}${NC}"
echo ""
echo -e "  ${BOLD}Useful commands:${NC}"
echo -e "    ${YELLOW}systemctl status download-manager${NC}   — status"
echo -e "    ${YELLOW}systemctl restart download-manager${NC}  — restart"
echo -e "    ${YELLOW}journalctl -u download-manager -f${NC}   — live logs"
echo -e "    ${YELLOW}nano ${CONFIG_DIR}/config.yml${NC}       — configuration"
echo ""
echo -e "  ${BOLD}Features:${NC}"
echo -e "    - AllDebrid : configure your API key in Settings"
echo -e "    - Torrents  : upload one or many .torrent files or magnets"
echo -e "    - Packages  : 2+ sources are grouped with one final notification"
echo -e "    - Media     : optional Plex or Jellyfin library refresh"
echo -e "    - Webhooks  : Discord, Slack, Telegram, Gotify, ntfy, Signal"
echo -e "    - 2FA       : enable from the Settings page"
echo -e "    - Updates   : from Settings > Updates"
echo ""
