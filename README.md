# Download Manager

Interface web de gestion de telechargements avec support **AllDebrid**, concue pour tourner sur des machines **Linux** (VM / LXC Proxmox, serveurs dedies, VPS).

![Python](https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![aria2](https://img.shields.io/badge/aria2-Download_Engine-blue)
![License](https://img.shields.io/badge/License-MIT-green)

---

## Fonctionnalites

- **Interface web moderne** — theme clair/sombre, responsive, temps reel via WebSocket
- **AllDebrid integre** — debridage automatique des liens hebergeurs (1fichier, Uptobox, etc.)
- **aria2 sous le capot** — telechargements rapides, multi-connexions, reprise automatique
- **Systeme de paquets** — groupez vos liens par saison, album, etc. (a la JDownloader)
- **Retry automatique** — 5 tentatives par defaut, delai entre chaque retry
- **Historique** — tous les telechargements termines/echoues sont conserves
- **Notifications webhook** — Discord, Slack, Telegram, Gotify, ntfy, ou generique JSON
- **Navigateur de fichiers** — selection et creation de dossiers directement depuis l'interface
- **Authentification** — login/mot de passe avec 2FA (OTP 6 chiffres)
- **Service systemd** — demarrage automatique, redemarrage en cas de crash

---

## Installation rapide

> **Pre-requis** : Ubuntu 20.04+ ou Debian 11+ (VM, LXC Proxmox, VPS). Acces root.

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Vayaris/download-manager/main/install.sh)
```

Le script installe automatiquement toutes les dependances (Python, aria2, etc.), configure le service systemd et demarre l'application.

---

## Installation manuelle

```bash
# 1. Cloner le depot
git clone https://github.com/Vayaris/download-manager.git
cd download-manager

# 2. Lancer l'installateur
sudo bash install.sh
```

---

## Utilisation

Apres installation, l'interface est accessible sur :

```
http://<IP_DE_VOTRE_MACHINE>:40320
```

Le port est configurable lors de l'installation.

### Commandes utiles

| Commande | Description |
|---|---|
| `systemctl status download-manager` | Statut du service |
| `systemctl restart download-manager` | Redemarrer |
| `systemctl stop download-manager` | Arreter |
| `journalctl -u download-manager -f` | Logs en temps reel |
| `nano /etc/download-manager/config.yml` | Modifier la configuration |

---

## Configuration

Le fichier de configuration se trouve dans `/etc/download-manager/config.yml` :

```yaml
server:
  host: "0.0.0.0"
  port: 40320

alldebrid:
  api_key: ""
  enabled: false

downloads:
  simultaneous: 3
  default_destination: "/opt/download-manager/downloads"
  allowed_paths:
    - "/mnt"
    - "/opt/download-manager/downloads"

auth:
  enabled: false
  jwt_secret: ""  # Auto-genere au premier lancement

aria2:
  rpc_port: 6800
  rpc_secret: "auto-generated"

webhooks:
  enabled: false
  url: ""
  format: "generic"  # generic | discord | slack | telegram | gotify | ntfy
  events:
    - "download_complete"
    - "download_failed"
    - "package_complete"
```

La plupart des parametres sont modifiables directement depuis la page **Parametres** de l'interface web.

---

## Fonctionnalites detaillees

### Systeme de paquets

Groupez plusieurs liens en un seul paquet (ex: une saison complete). Le paquet affiche la progression globale et se deplie pour montrer chaque fichier individuellement.

### Retry automatique

Chaque telechargement est automatiquement retente jusqu'a 5 fois en cas d'erreur. Un delai de 10 secondes est applique entre chaque tentative. Le compteur est visible dans l'interface.

### Notifications Webhook

Configurez une URL webhook pour recevoir des notifications lors des evenements :
- **Telechargement termine** / **echoue**
- **Paquet termine**

Formats supportes : Discord (embed), Slack (block), Telegram (Markdown), Gotify, ntfy, ou JSON generique.

### Authentification et 2FA

- Activez l'authentification depuis les parametres
- Creez un compte administrateur lors de la premiere activation
- Ajoutez la 2FA (TOTP) compatible Google Authenticator, Authy, etc.

---

## Mise a jour

```bash
cd /chemin/vers/download-manager
git pull
sudo bash install.sh
```

L'installateur detecte les installations existantes et met a jour sans ecraser votre configuration.

---

## Desinstallation

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

## Stack technique

| Composant | Role |
|---|---|
| **FastAPI** | Backend API + WebSocket |
| **aria2c** | Moteur de telechargement |
| **AllDebrid API** | Debridage de liens |
| **Vanilla JS** | Frontend (aucun framework) |
| **SQLite** | Base de donnees locale |
| **pyotp + qrcode** | 2FA / TOTP |

---

## Licence

MIT
