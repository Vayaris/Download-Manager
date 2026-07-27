# Download Manager

Self-hosted download manager powered by **FastAPI**, **aria2** and **AllDebrid**. It provides a responsive web/PWA interface for direct links, magnets and `.torrent` files, with real-time queue updates and optional Plex or Jellyfin library refreshes.

Current release: **v2.2.1**

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![aria2](https://img.shields.io/badge/aria2-Download_Engine-blue)
![PWA](https://img.shields.io/badge/PWA-Installable-0f766e?logo=pwa&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

## Highlights

- One unified form for direct links, magnets and one or many `.torrent` files through AllDebrid
- YouTube videos, Shorts, playlists and channels through AllDebrid, with searchable selection and batches up to 500 videos
- Optional direct YouTube engine powered by yt-dlp, with compatible MP4 and enriched multi-audio/subtitle MKV profiles
- Duplicate preflight for active URLs, successful history, destination files and repeated batch sources
- Automatic mixed packages when at least two sources are submitted, with one final package notification
- Queue priorities, drag and drop, pause/resume, configurable retries and up to 20 simultaneous downloads
- Download workspace with queue completion estimate, aggregate storage capacity and per-destination space warnings
- Page-wide link and magnet paste with `Ctrl+V`, plus five recent completed activities kept visible beside storage
- Global aria2 speed limit in MB/s, with effective-limit verification in Settings
- Responsive desktop/mobile interface with the v2 layout by default and a temporary v1 fallback, dark/light themes, French/English and installable PWA
- Account-synced destination explorer with favorites, recent paths, search, breadcrumbs and mobile tabs
- Silent `.nfo` filtering enabled by default
- Safe stalled-download watchdog and automatic history
- Responsive grouped history with batch summaries, quick filters, safe multi-selection and detailed error views
- Plex or Jellyfin integration with favorites, manual refresh suggestions and optional automatic refresh
- Webhooks for Discord, Slack, Telegram, Gotify, ntfy, Signal and generic JSON
- Mandatory authentication, optional TOTP 2FA, login rate limiting and IP blocking
- Persistent structured diagnostics, immutable releases with automatic rollback, SMB/CIFS support and admin CLI

## Requirements

- Ubuntu 20.04+ or Debian 11+
- Python 3.10 or newer
- Root access and systemd recommended
- A reachable download destination, usually under `/mnt` or `/opt/download-manager/downloads`
- An AllDebrid API key for debrid and torrent workflows
- Docker only when using the optional Signal integration
- A bundled ffmpeg and an application-local Deno only when using the optional direct YouTube engine; no system multimedia package is required

## Install

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Vayaris/download-manager/main/install.sh)
```

The installer asks for the HTTP port (`40320` by default), installs system dependencies, prepares an immutable release with its own Python environment, configures `download-manager.service` and `download-manager-aria2.service`, then starts the application. It does not configure, restart or modify Plex/Jellyfin services.

Open `http://<SERVER_IP>:40320` and create the administrator account on first launch.

To install from a local clone:

```bash
git clone https://github.com/Vayaris/Download-Manager.git
cd Download-Manager
sudo bash install.sh
```

## How downloads are grouped

Links, magnets and `.torrent` files share the same submission area. Torrent files can be selected or dropped anywhere on the form, reviewed before submission and mixed with pasted links. A custom batch name appears only when at least two sources are present.

| Submission | Result |
|---|---|
| One direct link, single-file magnet or single-file `.torrent` | Standalone download |
| One magnet or `.torrent` resolving to multiple files | One automatic package |
| Two or more valid sources, including mixed source types | One automatic package |
| Package members | One aggregate progress view and one final webhook |

AllDebrid resolves magnets and torrents before aria2 downloads the returned files. Remote AllDebrid caching is separate from the local aria2 speed limit. When `.nfo` filtering is enabled, matching files are ignored silently and never appear as failed or blocked items.

## YouTube downloads

Paste one public YouTube video, Short, playlist or channel URL in the regular download composer. Download Manager first analyzes the source and opens a searchable selection dialog. Duplicate videos already active or completed are unchecked by default, the source order is preserved, and at most 500 videos can be submitted at once. Two or more selected videos become one package and therefore emit one final package notification.

A `watch` URL containing a playlist lets you choose between the current video and the full playlist. Channel URLs can be filtered to videos, Shorts, or both. Live, upcoming, private and otherwise unavailable entries are ignored.

Two engines are available:

- **AllDebrid:** attempted first when selected. Download Manager handles streaming choices and delayed links, then automatically falls back to its local direct engine when AllDebrid explicitly reports that YouTube is unsupported.
- **Direct (yt-dlp):** disabled by default. Enable it under **Settings > YouTube** after installing the checked dependencies. The compatible profile favors MP4/H.264 with audio; the enriched MKV profile keeps the best video, one best non-descriptive audio track per available language, all manual subtitles, and French/English automatic subtitles.

The direct engine defaults to two concurrent jobs and has a separate per-download speed limit in MB/s. Most public videos work anonymously, but YouTube can require authentication for selected videos or server IP addresses. In that case, import a Netscape-format `cookies.txt` under **Settings > YouTube**. Download Manager stores it as `/opt/download-manager/config/youtube-cookies.txt` with mode `0600`, never returns its contents through the API, and gives each yt-dlp worker a private temporary copy.

Cookie setup takes five steps:

1. Install [Get cookies.txt LOCALLY for Chrome/Chromium](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) or [cookies.txt for Firefox](https://addons.mozilla.org/firefox/addon/cookies-txt/).
2. Open a private/incognito window and sign in to YouTube, preferably with a dedicated account.
3. In the same tab, open [youtube.com/robots.txt](https://www.youtube.com/robots.txt).
4. Export `cookies.txt` with the extension, then close the private window without reopening that session.
5. Import the file under **Settings > YouTube**.

Download Manager validates the Netscape format and discards every non-YouTube cookie before storing the file. Follow the [official yt-dlp YouTube guide](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies) when renewing it. Do not install the obsolete Chrome extension named **Get cookies.txt** without **LOCALLY**; the yt-dlp project reports that old extension as malware.

## Duplicate protection

Every web submission runs through a preflight check. Conflicts include an identical active URL, a successful history entry, a file already present in the selected destination, or a repeated source inside the same batch. The resolution dialog supports **Ignore**, **Download anyway**, and **Replace** per item, plus an apply-to-all control. Overwriting an existing destination always requires an additional explicit confirmation.

Some final filenames are only known after AllDebrid resolves a source. Those downloads remain in a `duplicate_pending` state and prompt for a decision before aria2 starts the local transfer.

## Download history

The Downloads page separates active work from history with dedicated tabs. History entries are grouped by date, and package members stay under one expandable summary showing their aggregate status, size and destination. Quick filters cover all entries, today's completions and failures.

Item details expose the source, destination, timestamps and full error without leaving the page. Entries can be removed individually or through a safe selection mode; bulk history removal and the global clear action always preserve downloaded files. Disk deletion remains an explicit per-file action.

## Destination explorer

You can paste an allowed path such as `/mnt/media/Movies` directly or open the file browser. On desktop, the browser shows favorites, the folder tree and recent destinations side by side. On mobile, the same areas become tabs.

Favorites, their order and recent destinations are stored server-side for the authenticated account. Directory scans run outside the FastAPI event loop and use a bounded timeout/cache so a slow disk or mount is less likely to freeze the interface.

Only paths listed in `downloads.allowed_paths` can be browsed or selected.

## Plex and Jellyfin

Settings supports one active media provider at a time:

- **Plex:** server URL and Plex token
- **Jellyfin:** server URL and API key

The media tab lists libraries, allows favorites with drag-and-drop ordering, and suggests likely libraries from completed download destinations. Automatic refresh is disabled by default; when enabled, recommended libraries are refreshed only after the entire download queue has reached a terminal state.

If Jellyfin runs in Docker and sees different paths from Download Manager, add a path mapping in the Jellyfin settings. For example, map the host destination `/mnt/movies` to the container path `/media/movies`. Unmatched destinations are reported on the media page instead of triggering a global library scan.

Media credentials are stored server-side and are never returned to the browser. Download Manager calls the configured API but does not restart or reconfigure the media server.

## Notifications

The Webhooks section has a master on/off switch. Supported formats are Discord, Slack, Telegram, Gotify, ntfy, Signal and generic JSON. Events can be enabled for completed downloads, failed downloads and completed packages.

Members of a package do not emit individual completion notifications. The package sends one final event after all members have completed or failed.

## Configuration

The main configuration file is `/etc/download-manager/config.yml`. Most values should be managed from the web Settings page.

```yaml
server:
  host: "0.0.0.0"
  port: 40320
  cors_origins: []
  trusted_proxies: []

alldebrid:
  enabled: false
  api_key: ""

downloads:
  simultaneous: 3
  download_segments: 1
  speed_limit: 0
  max_retries: 3
  retry_delay_seconds: 5
  skip_nfo_files: true
  stalled_timeout_hours: 3
  default_destination: "/opt/download-manager/downloads"
  allowed_paths:
    - "/mnt"
    - "/opt/download-manager/downloads"

youtube:
  direct_enabled: false
  max_concurrent: 2
  speed_limit: 0
```

Important ranges and behavior:

| Setting | Accepted value | Notes |
|---|---|---|
| `simultaneous` | `1` to `20` | Concurrent local downloads |
| `download_segments` | `1` to `16` | Connections per file |
| `speed_limit` | `0` or MB/s | Aggregate local aria2 limit; `0` is unlimited |
| `max_retries` | `0` to `20` | Captured when a new download is created |
| `retry_delay_seconds` | `0` to `3600` | Delay between attempts |
| `stalled_timeout_hours` | `0` to `168` | No-progress timeout; `0` disables the watchdog |
| `youtube.max_concurrent` | `1` to `4` | Concurrent direct yt-dlp workers; default `2` |
| `youtube.speed_limit` | `0` or MB/s | Per direct YouTube download; `0` is unlimited |

Existing installations keep their configuration during installer updates. Missing keys are supplied by application defaults and saved when changed through the interface.

## Paths and service

| Path | Purpose |
|---|---|
| `/opt/download-manager/current` | Atomic link to the active immutable release |
| `/opt/download-manager/releases` | Current and previous application releases |
| `/opt/download-manager/venvs` | Versioned Python environments |
| `/opt/download-manager/config/downloads.db` | SQLite database |
| `/opt/download-manager/config/aria2.session` | aria2 recovery session |
| `/opt/download-manager/config/youtube-cookies.txt` | Optional YouTube authentication cookies; mode `0600` |
| `/etc/download-manager/config.yml` | Runtime configuration and integration secrets |
| `/var/lib/download-manager/repository.git` | Private bare repository used by verified updates |
| `/var/backups/download-manager` | Update configuration and SQLite backups |
| `/var/log/download-manager` | aria2/application logs |
| `/opt/download-manager/tools/deno/deno` | Verified Deno runtime for optional direct YouTube downloads |

Useful commands:

```bash
systemctl status download-manager
systemctl status download-manager-aria2
systemctl restart download-manager
journalctl -u download-manager -f
journalctl -u download-manager-aria2 -f
```

Admin CLI:

```bash
cd /opt/download-manager/current/backend
/opt/download-manager/venv/bin/python dm-cli.py reset-admin
/opt/download-manager/venv/bin/python dm-cli.py list-ips
/opt/download-manager/venv/bin/python dm-cli.py unblock 1.2.3.4
/opt/download-manager/venv/bin/python dm-cli.py unblock-all
```

## Updates

Use **Settings > Updates > Check for updates**. When a newer GitHub release is available, the interface shows its changelog, installs it, restarts Download Manager if required, and reloads the page.

Updates run in an independent systemd unit. The requested GitHub tag and commit are verified, then a fresh release and Python environment are prepared before the short service interruption. Download Manager snapshots the configuration, SQLite database and service units before switching atomic links. If FastAPI or aria2 does not pass its health check, the previous links, database, configuration and units are restored automatically. The two previous runtimes and three most recent update backups are retained.

Version 2 makes the modern interface the default and requires one new login so the browser can move the session into a secure HttpOnly cookie. **Old look v1** remains selectable in the account settings and will be kept through the v2.1 stabilization period; it will not be removed without explicit validation.

For a manual update:

```bash
git clone https://github.com/Vayaris/Download-Manager.git
cd Download-Manager
sudo bash install.sh --upgrade
```

Back up `/etc/download-manager/config.yml` and `/opt/download-manager/config/downloads.db` before a manual recovery or migration.

## Security notes

- Authentication is mandatory; TOTP 2FA can be enabled per account.
- Five failed login attempts within 15 minutes block the source IP for four hours.
- Browser sessions use HttpOnly, SameSite cookies; bearer JWTs remain available for the admin CLI. Sessions currently last seven days and are revoked after a password change.
- File operations are constrained to configured allowed paths.
- Webhook targets are checked to reduce SSRF risk.
- Dependencies are locked and audited in CI; browser assets, including fonts, are served locally.
- CORS is disabled by default. Configure explicit origins and trusted proxies when using a reverse proxy.
- Imported YouTube cookies are account credentials. They stay server-side with mode `0600`; use a dedicated account and delete them when no longer required.
- The service runs as `root` to support mounts and arbitrary configured destinations. Do not expose port `40320` directly to the public Internet; use a firewall and a properly configured HTTPS reverse proxy.

## Troubleshooting

```bash
systemctl status download-manager
journalctl -u download-manager -n 100 --no-pager
tail -n 100 /var/log/download-manager/aria2.log
```

If a destination is unavailable, verify the mount first and confirm that its path is included in `downloads.allowed_paths`. For speed-limit issues, use the status shown in Settings: it reports the value effectively read back from aria2, not the speed of AllDebrid's remote cache.

If the interface reports that only the real-time connection is unavailable while downloads still work, enable WebSocket forwarding for `/ws/downloads` in the reverse proxy. In Nginx Proxy Manager, turn on **Websockets Support** for the proxy host. The Downloads page falls back to a lightweight three-second HTTP snapshot poll after five seconds, but WebSocket support remains the preferred configuration.

## Architecture

Browser/PWA communicates with FastAPI over HTTP and authenticated WebSocket. FastAPI stores queue and account state in SQLite, delegates local transfers to the separately supervised aria2 RPC service, and uses AllDebrid for debrid/torrent/streaming resolution. Queue status calls are batched, WebSocket snapshots are emitted only when state changes, and AllDebrid network waits do not retain SQLite connections. Optional direct YouTube transfers run in isolated yt-dlp subprocesses so analysis and post-processing do not block the queue loop. The frontend is framework-free Vanilla JS.

This project is designed for a single self-hosted user. SQLite and the current service model are intentional for that scope.

## Résumé français

Download Manager centralise les liens directs, magnets, fichiers `.torrent` et URL YouTube dans un composeur unique responsive. Une vidéo, un Short, une playlist ou une chaîne YouTube peut être analysé puis filtré avant ajout ; plusieurs vidéos forment un lot unique avec une seule notification finale. Le mode AllDebrid prend en charge les flux et liens différés, tandis qu’un moteur direct yt-dlp facultatif propose une sortie MP4 compatible ou MKV enrichie. Les sources collées ou déposées sont identifiées avant l’envoi et, à partir de deux éléments, un lot unique est créé automatiquement. Un magnet ou fichier `.torrent` unique est également regroupé automatiquement lorsqu’il contient plusieurs fichiers. Quand la file est vide, la page propose les destinations favorites et récentes avec l’espace disque disponible ainsi que les dernières activités ; pendant un téléchargement, elle affiche un résumé global des transferts et de leur vitesse. La vue Historique regroupe les lots, propose des filtres rapides et permet de retirer plusieurs entrées sans supprimer les fichiers téléchargés. Les intégrations Plex/Jellyfin permettent enfin un rafraîchissement manuel ou automatique des bibliothèques lorsque toute la file est terminée.

L’interface v2 devient le style par défaut avec une navigation latérale sur ordinateur, un affichage pleine largeur et une adaptation aux écrans ultralarges. L’ancien look v1 reste temporairement disponible dans les paramètres du compte comme solution de secours.

L’installation rapide, les chemins, commandes et réglages indiqués ci-dessus sont identiques pour l’interface française. La configuration courante se fait principalement depuis **Paramètres**.

## License

MIT
