# Download Manager

A web-based download manager with **AllDebrid** support, designed to run on **Linux** machines (Proxmox VM/LXC, dedicated servers, VPS).

![Python](https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![aria2](https://img.shields.io/badge/aria2-Download_Engine-blue)
![PWA](https://img.shields.io/badge/PWA-Installable-5A0FC8?logo=pwa&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

---

## Features

- **Modern web interface** — light/dark theme, mobile responsive, real-time updates via WebSocket
- **Installable PWA** — add the app to your phone's home screen (Android / iOS)
- **Optimized mobile view** — compact card layout, touch navigation, bottom navigation bar
- **AllDebrid integration** — automatic link debriding (1fichier, Uptobox, etc.)
- **Torrent / Magnet support** — upload `.torrent` files or paste magnet links via AllDebrid, with automatic polling and download start
- **aria2 engine** — fast downloads, multi-segment (split), automatic resume
- **Multi-segment downloads** — up to 16 connections per file (JDownloader-style) to maximize speed
- **Speed limit** — throttle global bandwidth in MB/s
- **Package system** — group your links by season, album, etc. with global progress tracking
- **Automatic retry** — 5 attempts by default, with delay between retries
- **Automatic history** — completed/failed downloads are automatically moved to history
- **Webhook notifications** — Discord, Slack, Telegram, Gotify, ntfy, or generic JSON (with built-in setup guides)
- **File browser** — select and create folders directly from the interface
- **Secure authentication** — login/password with 2FA (6-digit OTP), rate limiting, IP blocking
- **Built-in updates** — check and install new versions from the Settings page, with changelog
- **Admin CLI** — reset admin account, manage blocked IPs from the command line
- **Systemd service** — auto-start, crash recovery
- **Multi-language** — English and French, switchable from Settings

---

## Security

- **JWT authentication** with 2FA (TOTP) — compatible with Google Authenticator, Authy, etc.
- **Rate limiting** — 5 login attempts in 15 min, automatic IP blocking for 4h
- **Authenticated WebSocket** — real-time connections require a valid token
- **Path traversal protection** — file browser restricted to allowed paths
- **Destination validation** — cannot download to an unauthorized path
- **SSRF webhook protection** — internal URLs (localhost, private IPs) are blocked
- **IP spoofing protection** — proxy headers only accepted from local proxies
- **No CORS wildcard** — CORS disabled by default, configurable if needed

---

## Quick Install

> **Requirements**: Ubuntu 20.04+ or Debian 11+ (VM, LXC Proxmox, VPS). Root access.

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Vayaris/download-manager/main/install.sh)
```

The script automatically installs all dependencies (Python, aria2, etc.), configures the systemd service, and starts the application.

---

## Manual Install

```bash
# 1. Clone the repository
git clone https://github.com/Vayaris/download-manager.git
cd download-manager

# 2. Run the installer
sudo bash install.sh
```

---

## Usage

After installation, the interface is accessible at:

```
http://<YOUR_SERVER_IP>:40320
```

The port is configurable during installation.

### Mobile

The application is a **PWA** (Progressive Web App). From your mobile browser:
- **Android**: Menu (⋮) → "Add to Home screen"
- **iOS**: Share button (↑) → "Add to Home Screen"

The app then launches like a native application, without the browser toolbar.

### Useful Commands

| Command | Description |
|---|---|
| `systemctl status download-manager` | Service status |
| `systemctl restart download-manager` | Restart |
| `systemctl stop download-manager` | Stop |
| `journalctl -u download-manager -f` | Real-time logs |
| `nano /etc/download-manager/config.yml` | Edit configuration |

### Admin CLI

```bash
cd /opt/download-manager/backend

# Reset admin account
python3 dm-cli.py reset-admin

# List blocked IPs
python3 dm-cli.py list-ips

# Unblock an IP
python3 dm-cli.py unblock 1.2.3.4

# Unblock all IPs
python3 dm-cli.py unblock-all
```

---

## Configuration

The configuration file is located at `/etc/download-manager/config.yml`:

```yaml
server:
  host: "0.0.0.0"
  port: 40320
  cors_origins: []          # Allowed CORS origins (empty = disabled)
  trusted_proxies: []       # Trusted reverse proxy IPs

alldebrid:
  api_key: ""
  enabled: false

downloads:
  simultaneous: 3           # 1-10 simultaneous downloads
  download_segments: 1      # 1-16 segments per file (multi-connection)
  speed_limit: 0            # MB/s (0 = unlimited)
  default_destination: "/opt/download-manager/downloads"
  allowed_paths:
    - "/mnt"
    - "/opt/download-manager/downloads"

auth:
  jwt_secret: ""            # Auto-generated on first launch

aria2:
  rpc_port: 6800
  rpc_secret: "auto-generated"

webhooks:
  enabled: false
  url: ""
  format: "generic"         # generic | discord | slack | telegram | gotify | ntfy
  events:
    - "download_complete"
    - "download_failed"
    - "package_complete"
```

Most settings can be changed directly from the **Settings** page in the web interface.

---

## Detailed Features

### Torrent / Magnet Support

Add torrents directly from the interface:
- **Magnet link** — paste one or more magnet links (auto-detected in the main textarea)
- **.torrent file** — upload a file via the modal with drag & drop
- The torrent is sent to AllDebrid for debriding. If already cached, downloads start instantly. Otherwise, the "Active torrents" section shows real-time progress (speed, seeders).
- Once ready, a package is automatically created with all files.

### Package System

Group multiple links into a single package (e.g., a complete season). The package shows global real-time progress (completed files, percentage, cumulative speed) and can be expanded to show each file individually.

### Multi-Segment Downloads

Each download can use up to 16 simultaneous connections to the server (`download_segments` setting). More segments = more speed, like JDownloader. Configurable in settings.

### Speed Limit

Throttle the global bandwidth of all downloads in MB/s. Useful to avoid saturating your connection. The limit is applied immediately via aria2.

### Automatic Retry

Each download is automatically retried up to 5 times on error. A 10-second delay is applied between attempts. The counter is visible in the interface.

### Automatic History

Completed or failed downloads are automatically moved to the "Completed" section. The download area only shows active / pending / paused files. When empty, it disappears.

### Webhook Notifications

Configure a webhook URL to receive notifications on events:
- **Download completed** / **failed**
- **Package completed**

Supported formats: Discord (embed), Slack (block), Telegram (Markdown), Gotify, ntfy, or generic JSON. Built-in setup guides are provided for each service.

### Authentication and 2FA

- Create an admin account on first launch
- Add 2FA (TOTP) compatible with Google Authenticator, Authy, etc.
- Rate limiting: 5 attempts in 15 min = IP blocked for 4h
- Reset via `dm-cli.py reset-admin`

---

## Updates

### From the interface (recommended)

Go to **Settings** → **Updates** → **Check for updates**. If a new version is available, the changelog is displayed and you can update with one click. The page reloads automatically after restart.

### From the command line

```bash
cd /path/to/download-manager
git pull
sudo bash install.sh
```

The installer detects existing installations and updates without overwriting your configuration.

---

## Uninstall

```bash
sudo systemctl stop download-manager
sudo systemctl disable download-manager
sudo rm /etc/systemd/system/download-manager.service
sudo systemctl daemon-reload
sudo rm -rf /opt/download-manager
sudo rm -rf /etc/download-manager
sudo rm -rf /var/log/download-manager
```

---

## Tech Stack

| Component | Role |
|---|---|
| **FastAPI** | Backend API + WebSocket |
| **aria2c** | Download engine |
| **AllDebrid API** | Link debriding + torrents |
| **Vanilla JS** | PWA frontend (no framework) |
| **SQLite** | Local database |
| **pyotp + qrcode** | 2FA / TOTP |
| **python-jose** | JWT tokens |
| **bcrypt** | Password hashing |

---

## License

MIT

---

<details>
<summary>🇫🇷 Version française</summary>

# Download Manager

Interface web de gestion de téléchargements avec support **AllDebrid**, conçue pour tourner sur des machines **Linux** (VM / LXC Proxmox, serveurs dédiés, VPS).

## Fonctionnalités

- **Interface web moderne** — thème clair/sombre, responsive mobile, temps réel via WebSocket
- **PWA installable** — ajoutez l'app sur l'écran d'accueil de votre téléphone (Android / iOS)
- **AllDebrid intégré** — débridage automatique des liens hébergeurs
- **Support Torrent / Magnet** — upload de fichiers `.torrent` ou liens magnet via AllDebrid
- **aria2 sous le capot** — téléchargements rapides, multi-segments, reprise automatique
- **Multi-segments** — jusqu'à 16 connexions par fichier pour maximiser la vitesse
- **Système de paquets** — groupez vos liens par saison, album, etc.
- **Retry automatique** — 5 tentatives par défaut
- **Historique automatique** — les téléchargements terminés passent dans l'historique
- **Notifications webhook** — Discord, Slack, Telegram, Gotify, ntfy
- **Authentification sécurisée** — login avec 2FA (OTP), rate limiting, blocage IP
- **Mise à jour intégrée** — depuis la page Paramètres
- **Multi-langue** — anglais et français, changeable dans les Paramètres

## Installation rapide

> **Pré-requis** : Ubuntu 20.04+ ou Debian 11+. Accès root.

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Vayaris/download-manager/main/install.sh)
```

## Utilisation

Après installation, l'interface est accessible sur `http://<IP>:40320`.

### Commandes utiles

| Commande | Description |
|---|---|
| `systemctl status download-manager` | Statut du service |
| `systemctl restart download-manager` | Redémarrer |
| `journalctl -u download-manager -f` | Logs en temps réel |
| `nano /etc/download-manager/config.yml` | Configuration |

## Licence

MIT

</details>
