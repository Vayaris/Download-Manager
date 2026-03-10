#!/usr/bin/env bash
# ============================================================
#  Download Manager — Script d'installation
#  Compatible : Ubuntu 20.04+, Debian 11+ (VM / LXC Proxmox)
# ============================================================
set -eo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; NC='\033[0m'; BOLD='\033[1m'

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERR]${NC}   $*"; }
die()     { error "$*"; exit 1; }

# ---- Root check ----
[[ $EUID -eq 0 ]] || die "Ce script doit etre execute en tant que root. Utilisez : sudo bash install.sh"

# ---- Banner ----
echo ""
echo -e "${BOLD}╔═══════════════════════════════════════╗${NC}"
echo -e "${BOLD}║       Download Manager — Install      ║${NC}"
echo -e "${BOLD}╚═══════════════════════════════════════╝${NC}"
echo ""

# ---- Detect execution context (local clone vs bash <(curl ...)) ----
INSTALL_DIR="/opt/download-manager"
CONFIG_DIR="/etc/download-manager"
LOG_DIR="/var/log/download-manager"
CLONED_TEMP=""

# Try to resolve SCRIPT_DIR from BASH_SOURCE
_raw_source="${BASH_SOURCE[0]}"
if [[ "$_raw_source" == /dev/fd/* ]] || [[ "$_raw_source" == /proc/* ]] || [ -z "$_raw_source" ]; then
    # Running via bash <(curl ...) or pipe — must clone the repo
    SCRIPT_DIR=""
else
    SCRIPT_DIR="$(cd "$(dirname "$_raw_source")" && pwd)"
fi

# If SCRIPT_DIR is empty or doesn't contain project files, clone from GitHub
if [ -z "${SCRIPT_DIR}" ] || [ ! -f "${SCRIPT_DIR}/requirements.txt" ]; then
    info "Telechargement du projet depuis GitHub..."
    apt-get update -qq > /dev/null 2>&1
    apt-get install -y -qq git > /dev/null 2>&1
    CLONED_TEMP="$(mktemp -d)"
    git clone --depth 1 https://github.com/Vayaris/Download-Manager.git "${CLONED_TEMP}/download-manager"
    SCRIPT_DIR="${CLONED_TEMP}/download-manager"
    success "Projet telecharge"
    echo ""
fi

# ---- Port selection ----
DEFAULT_PORT=40320
read -rp "Sur quel port exposer l'interface web ? [${DEFAULT_PORT}] : " INPUT_PORT
PORT="${INPUT_PORT:-$DEFAULT_PORT}"

if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
    warn "Port invalide, utilisation du port par defaut : ${DEFAULT_PORT}"
    PORT=$DEFAULT_PORT
fi

info "Port selectionne : ${PORT}"
echo ""

# ---- System dependencies ----
info "Mise a jour des paquets..."
apt-get update -qq

info "Installation des dependances systeme..."
apt-get install -y -qq \
    python3 \
    python3-pip \
    python3-venv \
    aria2 \
    curl \
    wget \
    git \
    ca-certificates \
    > /dev/null 2>&1

# Check Python version
PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 8 ]); then
    die "Python 3.8+ requis. Version trouvee : ${PYTHON_VERSION}"
fi

success "Python ${PYTHON_VERSION} detecte"

# Verify aria2c is actually installed
if ! command -v aria2c &> /dev/null; then
    die "aria2c n'a pas ete installe correctement. Verifiez votre gestionnaire de paquets."
fi
success "aria2c $(aria2c --version | head -1 | awk '{print $3}') installe"

# Check if the selected port is already in use (warning only)
if command -v ss &> /dev/null; then
    if ss -tlnp | grep -q ":${PORT} " 2>/dev/null; then
        warn "Le port ${PORT} est deja utilise. Le service pourrait ne pas demarrer."
    fi
fi

# ---- Create directories ----
info "Creation de la structure de repertoires..."
mkdir -p "${INSTALL_DIR}"/{backend,frontend,downloads,config}
mkdir -p "${INSTALL_DIR}/backend"/{routers,services}
mkdir -p "${INSTALL_DIR}/frontend/static"/{css,js}
mkdir -p "${CONFIG_DIR}"
mkdir -p "${LOG_DIR}"

# ---- Copy project files ----
info "Copie des fichiers du projet..."
cp -r "${SCRIPT_DIR}/backend/"* "${INSTALL_DIR}/backend/"
cp -r "${SCRIPT_DIR}/frontend/"* "${INSTALL_DIR}/frontend/"
cp "${SCRIPT_DIR}/requirements.txt" "${INSTALL_DIR}/"
cp "${SCRIPT_DIR}/start.sh" "${INSTALL_DIR}/start.sh"
chmod +x "${INSTALL_DIR}/start.sh"
[ -f "${SCRIPT_DIR}/VERSION" ] && cp "${SCRIPT_DIR}/VERSION" "${INSTALL_DIR}/VERSION"
success "Fichiers copies"

# ---- Generate aria2 secret ----
ARIA2_SECRET=$(tr -dc 'a-zA-Z0-9' < /dev/urandom | fold -w 32 | head -n 1)

# ---- Config file ----
if [ -f "${CONFIG_DIR}/config.yml" ]; then
    info "Configuration existante detectee, mise a jour du port uniquement."
    sed -i "s/^\(\s*port:\s*\).*/\1${PORT}/" "${CONFIG_DIR}/config.yml"

    # Add webhooks section if missing
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
        info "Section webhooks ajoutee a la configuration"
    fi
else
    info "Creation du fichier de configuration..."
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
    success "Configuration creee : ${CONFIG_DIR}/config.yml"
fi

# ---- Python virtual environment ----
if [ -d "${INSTALL_DIR}/venv" ]; then
    info "Virtualenv existant, mise a jour..."
else
    info "Creation du virtualenv Python..."
    python3 -m venv "${INSTALL_DIR}/venv" > /dev/null 2>&1
    success "Virtualenv cree"
fi

info "Installation des dependances Python..."
"${INSTALL_DIR}/venv/bin/pip" install --quiet --upgrade pip
"${INSTALL_DIR}/venv/bin/pip" install --quiet -r "${INSTALL_DIR}/requirements.txt"
success "Dependances Python installees"

# ---- systemd service ----
info "Configuration du service systemd..."
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

systemctl daemon-reload
systemctl enable download-manager > /dev/null 2>&1
success "Service systemd configure et active"

# ---- Git repo for auto-updates ----
if [ ! -d "${INSTALL_DIR}/.git" ]; then
    info "Configuration du depot git pour les mises a jour..."
    git clone --depth 1 https://github.com/Vayaris/Download-Manager.git "${INSTALL_DIR}/.git-tmp" > /dev/null 2>&1 && \
        mv "${INSTALL_DIR}/.git-tmp/.git" "${INSTALL_DIR}/.git" && \
        rm -rf "${INSTALL_DIR}/.git-tmp" && \
        git -C "${INSTALL_DIR}" reset --hard HEAD > /dev/null 2>&1 && \
        success "Depot git configure pour les mises a jour" || \
        warn "Impossible de configurer le depot git (mises a jour manuelles uniquement)"
fi

# ---- Start ----
info "Demarrage du service..."
systemctl restart download-manager

sleep 3
if systemctl is-active --quiet download-manager; then
    success "Service demarre avec succes"
else
    warn "Le service n'a pas demarre. Verifiez : journalctl -u download-manager -n 30"
fi

# ---- Cleanup temp clone ----
if [ -n "${CLONED_TEMP}" ] && [ -d "${CLONED_TEMP}" ]; then
    rm -rf "${CLONED_TEMP}"
fi

# ---- Summary ----
SERVER_IP=$(hostname -I | awk '{print $1}')

echo ""
echo -e "${BOLD}╔═══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║         Installation terminee avec succes !       ║${NC}"
echo -e "${BOLD}╚═══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Interface web :  ${BOLD}${GREEN}http://${SERVER_IP}:${PORT}${NC}"
echo ""
echo -e "  Commandes utiles :"
echo -e "    ${YELLOW}systemctl status download-manager${NC}   — statut"
echo -e "    ${YELLOW}systemctl restart download-manager${NC}  — redemarrer"
echo -e "    ${YELLOW}journalctl -u download-manager -f${NC}   — logs"
echo -e "    ${YELLOW}nano ${CONFIG_DIR}/config.yml${NC}       — configuration"
echo ""
echo -e "  Fonctionnalites :"
echo -e "    - AllDebrid : configurez votre cle dans ${BOLD}Parametres${NC}"
echo -e "    - Torrents  : upload .torrent ou magnet via AllDebrid"
echo -e "    - Paquets   : groupez vos liens en paquets"
echo -e "    - Webhooks  : Discord, Slack, Telegram, Gotify, ntfy"
echo -e "    - 2FA       : activez depuis la page Parametres"
echo -e "    - Mise a jour : depuis Parametres > Mise a jour"
echo ""
