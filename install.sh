#!/usr/bin/env bash
# ============================================================
#  Download Manager — Script d'installation
#  Compatible : Ubuntu 20.04+, Debian 11+ (VM / LXC Proxmox)
# ============================================================
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; NC='\033[0m'; BOLD='\033[1m'

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERR]${NC}   $*"; }
die()     { error "$*"; exit 1; }

# ---- Root check ----
[[ $EUID -eq 0 ]] || die "Ce script doit être exécuté en tant que root. Utilisez : sudo bash install.sh"

# ---- Banner ----
echo ""
echo -e "${BOLD}╔═══════════════════════════════════════╗${NC}"
echo -e "${BOLD}║       Download Manager — Install      ║${NC}"
echo -e "${BOLD}╚═══════════════════════════════════════╝${NC}"
echo ""

# ---- Port selection ----
DEFAULT_PORT=40320
read -rp "Sur quel port exposer l'interface web ? [${DEFAULT_PORT}] : " INPUT_PORT
PORT="${INPUT_PORT:-$DEFAULT_PORT}"

if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
    warn "Port invalide, utilisation du port par défaut : ${DEFAULT_PORT}"
    PORT=$DEFAULT_PORT
fi

info "Port sélectionné : ${PORT}"
echo ""

# ---- Directories ----
INSTALL_DIR="/opt/download-manager"
CONFIG_DIR="/etc/download-manager"
LOG_DIR="/var/log/download-manager"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---- System dependencies ----
info "Mise à jour des paquets..."
apt-get update -qq

info "Installation des dépendances système..."
apt-get install -y -qq \
    python3 \
    python3-pip \
    python3-venv \
    aria2 \
    curl \
    wget \
    ca-certificates \
    > /dev/null 2>&1

# Check Python version
PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 8 ]); then
    die "Python 3.8+ requis. Version trouvée : ${PYTHON_VERSION}"
fi

success "Python ${PYTHON_VERSION} détecté"
success "aria2c $(aria2c --version | head -1 | awk '{print $3}') installé"

# ---- Create directories ----
info "Création de la structure de répertoires..."
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
success "Fichiers copiés"

# ---- Generate aria2 secret ----
ARIA2_SECRET=$(tr -dc 'a-zA-Z0-9' < /dev/urandom | fold -w 32 | head -n 1)

# ---- Config file ----
if [ -f "${CONFIG_DIR}/config.yml" ]; then
    info "Configuration existante détectée, mise à jour du port uniquement."
    sed -i "s/^\(\s*port:\s*\).*/\1${PORT}/" "${CONFIG_DIR}/config.yml"
else
    info "Création du fichier de configuration..."
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
  username: "admin"
  password_hash: ""

aria2:
  rpc_port: 6800
  rpc_secret: "${ARIA2_SECRET}"
EOF
    success "Configuration créée : ${CONFIG_DIR}/config.yml"
fi

# ---- Python virtual environment ----
if [ -d "${INSTALL_DIR}/venv" ]; then
    info "Virtualenv existant, mise à jour..."
else
    info "Création du virtualenv Python..."
    python3 -m venv "${INSTALL_DIR}/venv" > /dev/null 2>&1
    success "Virtualenv créé"
fi

info "Installation des dépendances Python..."
"${INSTALL_DIR}/venv/bin/pip" install --quiet --upgrade pip
"${INSTALL_DIR}/venv/bin/pip" install --quiet -r "${INSTALL_DIR}/requirements.txt"
success "Dépendances Python installées"

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
success "Service systemd configuré et activé"

# ---- Start ----
info "Démarrage du service..."
systemctl restart download-manager

sleep 3
if systemctl is-active --quiet download-manager; then
    success "Service démarré avec succès"
else
    warn "Le service n'a pas démarré. Vérifiez : journalctl -u download-manager -n 30"
fi

# ---- Summary ----
SERVER_IP=$(hostname -I | awk '{print $1}')

echo ""
echo -e "${BOLD}╔═══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║         Installation terminée avec succès !       ║${NC}"
echo -e "${BOLD}╚═══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Interface web :  ${BOLD}${GREEN}http://${SERVER_IP}:${PORT}${NC}"
echo ""
echo -e "  Commandes utiles :"
echo -e "    ${YELLOW}systemctl status download-manager${NC}   — statut"
echo -e "    ${YELLOW}systemctl restart download-manager${NC}  — redémarrer"
echo -e "    ${YELLOW}journalctl -u download-manager -f${NC}   — logs"
echo -e "    ${YELLOW}nano ${CONFIG_DIR}/config.yml${NC}       — configuration"
echo ""
echo -e "  Activez AllDebrid depuis la page ${BOLD}Paramètres${NC} de l'interface."
echo ""
