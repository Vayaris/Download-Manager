# Download Manager

Interface web de gestion de téléchargements avec support **AllDebrid**, conçue pour tourner sur des machines **Linux** (VM / LXC Proxmox, serveurs dédiés, VPS).

![Python](https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![aria2](https://img.shields.io/badge/aria2-Download_Engine-blue)
![PWA](https://img.shields.io/badge/PWA-Installable-5A0FC8?logo=pwa&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

---

## Fonctionnalités

- **Interface web moderne** — thème clair/sombre, responsive mobile, temps réel via WebSocket
- **PWA installable** — ajoutez l'app sur l'écran d'accueil de votre téléphone (Android / iOS)
- **Vue mobile optimisée** — layout carte compact, navigation tactile, barre de navigation bas d'écran
- **AllDebrid intégré** — débridage automatique des liens hébergeurs (1fichier, Uptobox, etc.)
- **aria2 sous le capot** — téléchargements rapides, multi-segments (split), reprise automatique
- **Multi-segments** — jusqu'à 16 connexions par fichier (style JDownloader) pour maximiser la vitesse
- **Limite de vitesse** — bridez la bande passante globale en Mo/s
- **Système de paquets** — groupez vos liens par saison, album, etc. avec suivi de progression global
- **Retry automatique** — 5 tentatives par défaut, délai entre chaque retry
- **Historique automatique** — les téléchargements terminés/échoués passent automatiquement dans l'historique
- **Notifications webhook** — Discord, Slack, Telegram, Gotify, ntfy, ou générique JSON (avec guides de configuration intégrés)
- **Navigateur de fichiers** — sélection et création de dossiers directement depuis l'interface
- **Authentification sécurisée** — login/mot de passe avec 2FA (OTP 6 chiffres), rate limiting, blocage IP
- **CLI d'administration** — reset admin, gestion des IPs bloquées en ligne de commande
- **Service systemd** — démarrage automatique, redémarrage en cas de crash

---

## Sécurité

- **Authentification JWT** avec 2FA (TOTP) — compatible Google Authenticator, Authy, etc.
- **Rate limiting** — 5 tentatives de login en 15 min, blocage IP automatique pendant 4h
- **WebSocket authentifié** — les connexions temps réel requièrent un token valide
- **Protection path traversal** — navigation fichiers restreinte aux chemins autorisés
- **Validation des destinations** — impossible de télécharger vers un chemin non autorisé
- **Protection SSRF webhook** — les URLs internes (localhost, IPs privées) sont bloquées
- **Protection IP spoofing** — les headers proxy ne sont acceptés que depuis des proxys locaux
- **Pas de CORS wildcard** — CORS désactivé par défaut, configurable si nécessaire

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

### Sur mobile

L'application est une **PWA** (Progressive Web App). Depuis votre navigateur mobile :
- **Android** : Menu (⋮) → "Ajouter à l'écran d'accueil"
- **iOS** : Bouton partage (↑) → "Sur l'écran d'accueil"

L'app se lance ensuite comme une application native, sans barre de navigateur.

### Commandes utiles

| Commande | Description |
|---|---|
| `systemctl status download-manager` | Statut du service |
| `systemctl restart download-manager` | Redémarrer |
| `systemctl stop download-manager` | Arrêter |
| `journalctl -u download-manager -f` | Logs en temps réel |
| `nano /etc/download-manager/config.yml` | Modifier la configuration |

### CLI d'administration

```bash
cd /opt/download-manager/backend

# Réinitialiser le compte admin
python3 dm-cli.py reset-admin

# Lister les IPs bloquées
python3 dm-cli.py list-ips

# Débloquer une IP
python3 dm-cli.py unblock 1.2.3.4

# Débloquer toutes les IPs
python3 dm-cli.py unblock-all
```

---

## Configuration

Le fichier de configuration se trouve dans `/etc/download-manager/config.yml` :

```yaml
server:
  host: "0.0.0.0"
  port: 40320
  cors_origins: []          # Liste d'origines CORS autorisées (vide = désactivé)
  trusted_proxies: []       # IPs de reverse proxy de confiance

alldebrid:
  api_key: ""
  enabled: false

downloads:
  simultaneous: 3           # 1-10 téléchargements simultanés
  download_segments: 1      # 1-16 segments par fichier (multi-connexion)
  speed_limit: 0            # Mo/s (0 = illimité)
  default_destination: "/opt/download-manager/downloads"
  allowed_paths:
    - "/mnt"
    - "/opt/download-manager/downloads"

auth:
  jwt_secret: ""            # Auto-généré au premier lancement

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

La plupart des paramètres sont modifiables directement depuis la page **Paramètres** de l'interface web.

---

## Fonctionnalités détaillées

### Système de paquets

Groupez plusieurs liens en un seul paquet (ex : une saison complète). Le paquet affiche la progression globale en temps réel (nombre de fichiers terminés, pourcentage, vitesse cumulée) et se déplie pour montrer chaque fichier individuellement.

### Multi-segments

Chaque téléchargement peut utiliser jusqu'à 16 connexions simultanées vers le serveur (paramètre `download_segments`). Plus de segments = plus de vitesse, comme JDownloader. Configurable par section dans les paramètres.

### Limite de vitesse

Bridez la bande passante globale de tous les téléchargements en Mo/s. Utile pour ne pas saturer votre connexion. La limite s'applique immédiatement via aria2.

### Retry automatique

Chaque téléchargement est automatiquement retenté jusqu'à 5 fois en cas d'erreur. Un délai de 10 secondes est appliqué entre chaque tentative. Le compteur est visible dans l'interface.

### Historique automatique

Les téléchargements terminés ou échoués sont automatiquement déplacés vers la section "Terminés". La zone de téléchargement ne montre que les fichiers en cours / en attente / en pause. Quand elle est vide, elle disparaît.

### Notifications Webhook

Configurez une URL webhook pour recevoir des notifications lors des événements :
- **Téléchargement terminé** / **échoué**
- **Paquet terminé**

Formats supportés : Discord (embed), Slack (block), Telegram (Markdown), Gotify, ntfy, ou JSON générique. Des guides de configuration intégrés vous accompagnent pour chaque service.

### Authentification et 2FA

- Créez un compte administrateur au premier lancement
- Ajoutez la 2FA (TOTP) compatible Google Authenticator, Authy, etc.
- Rate limiting : 5 tentatives en 15 min = blocage IP pendant 4h
- Réinitialisation possible via `dm-cli.py reset-admin`

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
| **Vanilla JS** | Frontend PWA (aucun framework) |
| **SQLite** | Base de données locale |
| **pyotp + qrcode** | 2FA / TOTP |
| **python-jose** | JWT tokens |
| **bcrypt** | Hachage mots de passe |

---

## Licence

MIT
