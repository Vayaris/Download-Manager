# Download Manager

Interface web de gestion de téléchargements avec support **AllDebrid**, conçue pour tourner sur des machines **Linux** (VM / LXC Proxmox, serveurs dédiés, VPS).

![Python](https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![aria2](https://img.shields.io/badge/aria2-Download_Engine-blue)
![License](https://img.shields.io/badge/License-MIT-green)

---

## Fonctionnalités

- **Interface web moderne** — thème clair/sombre, responsive, temps réel via WebSocket
- **AllDebrid intégré** — débridage automatique des liens hébergeurs (1fichier, Uptobox, etc.)
- **aria2 sous le capot** — téléchargements rapides, multi-connexions, reprise automatique
- **Système de paquets** — groupez vos liens par saison, album, etc. (à la JDownloader)
- **Retry automatique** — 5 tentatives par défaut, délai entre chaque retry
- **Historique** — tous les téléchargements terminés/échoués sont conservés
- **Notifications webhook** — Discord, Slack, Telegram, Gotify, ntfy, ou générique JSON
- **Navigateur de fichiers** — sélection et création de dossiers directement depuis l'interface
- **Authentification** — login/mot de passe avec 2FA (OTP 6 chiffres)
- **Service systemd** — démarrage automatique, redémarrage en cas de crash

---

## Installation rapide

> **Pré-requis** : Ubuntu 20.04+ ou Debian 11+ (VM, LXC Proxmox, VPS). Accès root.

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Vayaris/download-manager/main/install.sh)
```

Le script installe automatiquement toutes les dépendances (Python, aria2, etc.), configure le service systemd et démarre l'application.

---

## Installation manuelle

```bash
# 1. Cloner le dépôt
git clone https://github.com/Vayaris/download-manager.git
cd download-manager

# 2. Lancer l'installateur
sudo bash install.sh
```

---

## Utilisation

Après installation, l'interface est accessible sur :

```
http://<IP_DE_VOTRE_MACHINE>:40320
```

Le port est configurable lors de l'installation.

### Commandes utiles

| Commande | Description |
|---|---|
| `systemctl status download-manager` | Statut du service |
| `systemctl restart download-manager` | Redémarrer |
| `systemctl stop download-manager` | Arrêter |
| `journalctl -u download-manager -f` | Logs en temps réel |
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
  jwt_secret: ""  # Auto-généré au premier lancement

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

La plupart des paramètres sont modifiables directement depuis la page **Paramètres** de l'interface web.

---

## Fonctionnalités détaillées

### Système de paquets

Groupez plusieurs liens en un seul paquet (ex : une saison complète). Le paquet affiche la progression globale et se déplie pour montrer chaque fichier individuellement.

### Retry automatique

Chaque téléchargement est automatiquement retenté jusqu'à 5 fois en cas d'erreur. Un délai de 10 secondes est appliqué entre chaque tentative. Le compteur est visible dans l'interface.

### Notifications Webhook

Configurez une URL webhook pour recevoir des notifications lors des événements :
- **Téléchargement terminé** / **échoué**
- **Paquet terminé**

Formats supportés : Discord (embed), Slack (block), Telegram (Markdown), Gotify, ntfy, ou JSON générique.

### Authentification et 2FA

- Activez l'authentification depuis les paramètres
- Créez un compte administrateur lors de la première activation
- Ajoutez la 2FA (TOTP) compatible Google Authenticator, Authy, etc.

---

## Mise à jour

```bash
cd /chemin/vers/download-manager
git pull
sudo bash install.sh
```

L'installateur détecte les installations existantes et met à jour sans écraser votre configuration.

---

## Désinstallation

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

| Composant | Rôle |
|---|---|
| **FastAPI** | Backend API + WebSocket |
| **aria2c** | Moteur de téléchargement |
| **AllDebrid API** | Débridage de liens |
| **Vanilla JS** | Frontend (aucun framework) |
| **SQLite** | Base de données locale |
| **pyotp + qrcode** | 2FA / TOTP |

---

## Licence

MIT
