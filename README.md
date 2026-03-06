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
- **Navigateur de fichiers** — sélection du dossier de destination directement depuis l'interface
- **Authentification optionnelle** — protégez l'accès avec login/mot de passe
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
  api_key: ""        # Votre clé API AllDebrid
  enabled: false

downloads:
  simultaneous: 3    # Téléchargements simultanés (1-5)
  default_destination: "/opt/download-manager/downloads"
  allowed_paths:
    - "/mnt"
    - "/opt/download-manager/downloads"

auth:
  enabled: false
  username: "admin"
  password_hash: ""
```

La plupart des paramètres sont modifiables directement depuis la page **Paramètres** de l'interface web.

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

---

## Licence

MIT
