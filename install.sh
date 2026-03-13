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
read -rp "Which port should the web interface listen on? [${DEFAULT_PORT}] : " INPUT_PORT
PORT="${INPUT_PORT:-$DEFAULT_PORT}"

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
if [ "$PYTHON_MAJOR" -lt 3 ] || ( [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 8 ] ); then
    die "Python 3.8+ required. Found: ${PYTHON_VERSION}"
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
mkdir -p "${INSTALL_DIR}"/{backend,frontend,downloads,config}
mkdir -p "${INSTALL_DIR}/backend"/{routers,services}
mkdir -p "${INSTALL_DIR}/frontend/static"/{css,js}
mkdir -p "${CONFIG_DIR}"
mkdir -p "${LOG_DIR}"

# ---- Copy project files ----
info "Copying project files..."
cp -r "${SCRIPT_DIR}/backend/"*   "${INSTALL_DIR}/backend/"
cp -r "${SCRIPT_DIR}/frontend/"*  "${INSTALL_DIR}/frontend/"
cp    "${SCRIPT_DIR}/requirements.txt" "${INSTALL_DIR}/"
cp    "${SCRIPT_DIR}/start.sh"    "${INSTALL_DIR}/start.sh"
chmod +x "${INSTALL_DIR}/start.sh"
[ -f "${SCRIPT_DIR}/VERSION" ] && cp "${SCRIPT_DIR}/VERSION" "${INSTALL_DIR}/VERSION"
success "Files copied"

# ---- Generate aria2 secret ----
ARIA2_SECRET=$(tr -dc 'a-zA-Z0-9' < /dev/urandom | head -c 32)

# ---- Config file ----
if [ -f "${CONFIG_DIR}/config.yml" ]; then
    info "Existing configuration detected, updating port only."
    sed -i "s/^\(\s*port:\s*\).*/\1${PORT}/" "${CONFIG_DIR}/config.yml"
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

alldebrid:
  api_key: ""
  enabled: false

downloads:
  simultaneous: 3
  default_destination: "${INSTALL_DIR}/downloads"
  allowed_paths:
    - "/mnt"
    - "${INSTALL_DIR}/downloads"

auth:
  enabled: false
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
EOF
    success "Configuration created: ${CONFIG_DIR}/config.yml"
fi

# ---- systemd service (created BEFORE pip install) ----
info "Configuring systemd service..."
cat > /etc/systemd/system/download-manager.service <<EOF
[Unit]
Description=Download Manager
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}

Environment=DM_CONFIG=${CONFIG_DIR}/config.yml
Environment=DM_DB=${INSTALL_DIR}/config/downloads.db

ExecStart=${INSTALL_DIR}/start.sh
ExecStopPost=/bin/bash -c 'pkill -f "aria2c.*rpc-listen-port" 2>/dev/null || true'

Restart=on-failure
RestartSec=5
StartLimitIntervalSec=60
StartLimitBurst=5

StandardOutput=journal
StandardError=journal
SyslogIdentifier=download-manager

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd (works on both VM and LXC)
if command -v systemctl >/dev/null 2>&1 && systemctl --version >/dev/null 2>&1; then
    systemctl daemon-reload
    systemctl enable download-manager 2>/dev/null || true
    success "Systemd service configured and enabled"
    HAVE_SYSTEMD=1
else
    warn "systemctl not available — service file written but could not be enabled automatically"
    HAVE_SYSTEMD=0
fi

# ---- Python virtual environment ----
if [ -d "${INSTALL_DIR}/venv" ]; then
    info "Existing virtualenv found, updating..."
else
    info "Creating Python virtualenv..."
    if ! python3 -m venv "${INSTALL_DIR}/venv"; then
        warn "python3 -m venv failed, trying python3-venv package..."
        apt-get install -y python3-venv python3-full 2>/dev/null || true
        if ! python3 -m venv "${INSTALL_DIR}/venv"; then
            die "Failed to create Python virtualenv. Try: apt-get install python3-venv"
        fi
    fi
    success "Virtualenv created"
fi

info "Upgrading pip..."
"${INSTALL_DIR}/venv/bin/pip" install --upgrade pip --quiet || true

info "Installing Python dependencies (this may take several minutes due to native compilation)..."
if ! "${INSTALL_DIR}/venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"; then
    error "pip install failed. Trying with verbose output..."
    "${INSTALL_DIR}/venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt" --no-cache-dir \
        || die "Failed to install Python dependencies. Check the errors above."
fi
success "Python dependencies installed"

# ---- Git repo for auto-updates ----
if [ ! -d "${INSTALL_DIR}/.git" ]; then
    info "Setting up git repository for future updates..."
    GITTMP="$(mktemp -d)"
    if git clone --depth 1 https://github.com/Vayaris/Download-Manager.git "${GITTMP}/repo" >/dev/null 2>&1; then
        mv "${GITTMP}/repo/.git" "${INSTALL_DIR}/.git"
        rm -rf "${GITTMP}"
        git -C "${INSTALL_DIR}" reset --hard HEAD >/dev/null 2>&1 || true
        success "Git repository configured for future updates"
    else
        warn "Could not set up git repository (in-app updates will not be available)"
        rm -rf "${GITTMP}" 2>/dev/null || true
    fi
fi

# ---- Start service ----
if [ "${HAVE_SYSTEMD:-0}" -eq 1 ]; then
    info "Starting Download Manager service..."
    systemctl reset-failed download-manager 2>/dev/null || true
    if systemctl restart download-manager; then
        # Wait up to 10 seconds for service to become active
        for i in 1 2 3 4 5 6 7 8 9 10; do
            sleep 1
            if systemctl is-active --quiet download-manager; then
                success "Service started successfully"
                break
            fi
            if [ "$i" -eq 10 ]; then
                warn "Service did not start within 10s. Check: journalctl -u download-manager -n 50"
            fi
        done
    else
        warn "Failed to start service. Check: journalctl -u download-manager -n 50"
    fi
else
    info "Starting Download Manager manually..."
    nohup "${INSTALL_DIR}/start.sh" >> "${LOG_DIR}/download-manager.log" 2>&1 &
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
echo -e "    - Torrents  : upload .torrent or magnet via AllDebrid"
echo -e "    - Packages  : group your links into packages"
echo -e "    - Webhooks  : Discord, Slack, Telegram, Gotify, ntfy, Signal"
echo -e "    - 2FA       : enable from the Settings page"
echo -e "    - Updates   : from Settings > Updates"
echo ""
