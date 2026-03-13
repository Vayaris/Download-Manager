// ============================================================
//  Download Manager — Internationalization (i18n)
// ============================================================

const TRANSLATIONS = {
  en: {
    // ---- Status labels ----
    status_pending: "Pending",
    status_downloading: "Downloading",
    status_paused: "Paused",
    status_complete: "Complete",
    status_error: "Error",
    status_failed: "Failed",
    status_debrid: "Debriding",

    // ---- General ----
    error_prefix: "Error: ",
    copy_ok: "Path copied!",
    copy_fail: "Unable to copy",
    paste_ok: "Link(s) pasted!",
    paste_empty: "Clipboard is empty",
    paste_fail: "Cannot access clipboard",

    // ---- Stats ----
    stats_files: "{{n}} file{{s}}",
    stats_active: "{{n}} active",
    stats_pending: "{{n}} pending",

    // ---- Packages ----
    pkg_files: "files",
    pkg_status_complete: "Complete",
    pkg_status_partial: "Partial",
    pkg_status_active: "In progress",
    pkg_deleted: "Package deleted",
    pkg_name_required: "Enter a package name",
    pkg_links_required: "Add some links",
    pkg_created: "Package \"{{name}}\" created with {{n}} link(s)",

    // ---- History ----
    history_prev: "Previous",
    history_next: "Next",
    history_confirm_clear: "Clear all history?",
    history_cleared: "History cleared",
    history_confirm_delete: "Remove this entry from history?",
    history_confirm_delete_file: "Remove this entry AND delete the file from disk?",
    history_deleted: "Entry removed",
    history_deleted_file: "Entry and file removed",

    // ---- Torrent ----
    torrent_nothing: "Paste a magnet link or select a .torrent file",
    torrent_added: "{{n}} torrent(s) added",
    torrent_deleted: "Torrent deleted",
    torrent_dropzone: "Click or drag a .torrent file here",

    // ---- Downloads ----
    links_empty: "Paste at least one link.",
    links_added: "{{n}} link{{s}} added to queue.",
    confirm_remove_all: "Remove all active downloads?",
    all_removed: "All downloads removed",
    btn_pause: "Pause",
    btn_resume: "Resume",
    btn_delete: "Delete",
    btn_delete_pkg: "Delete package",
    btn_delete_history: "Remove from history",
    btn_delete_file: "Delete file from disk",

    // ---- Login ----
    login_subtitle: "Sign in to access the dashboard",
    login_invalid: "Invalid credentials",
    login_otp_step: "Two-factor verification required",
    login_switch_account: "Switch account",
    login_server_error: "Server connection error",
    setup_username_required: "Username required",
    setup_password_min: "Password: 6 characters minimum",
    setup_password_mismatch: "Passwords do not match",
    setup_success: "Admin account created!",

    // ---- Date formatting ----
    date_locale: "en-US",

    // ---- Torrent status ----
    torrent_status_error: "Error",
    torrent_status_processing: "Processing",

    // ---- File browser ----
    fb_loading: "Loading...",
    fb_empty: "No subdirectories",
    fb_error: "Error: ",
    fb_folder_required: "Folder name required",
    fb_folder_created: "Folder \"{{name}}\" created",

    // ---- Account ----
    acct_title: "My account",
    acct_role: "Administrator",
    acct_change_password: "Change password",
    acct_password_placeholder: "New password (min. 6 characters)",
    acct_password_update: "Update",
    acct_password_min: "Password: 6 characters minimum",
    acct_password_updated: "Password updated",
    acct_2fa_title: "Two-factor authentication (2FA)",
    acct_2fa_enabled: "Enabled",
    acct_2fa_disabled: "Disabled",
    acct_2fa_enable_btn: "Enable 2FA",
    acct_2fa_scan_qr: "Scan this QR code with your authenticator app (Google Authenticator, Authy, etc.)",
    acct_2fa_manual_key: "Or enter this key manually:",
    acct_2fa_otp_placeholder: "6-digit OTP code",
    acct_2fa_verify: "Verify and enable",
    acct_2fa_activated: "2FA enabled successfully!",
    acct_2fa_invalid_code: "Invalid code",
    acct_2fa_enter_code: "Enter a 6-digit code",
    acct_2fa_disable_hint: "2FA is enabled. Enter your current OTP code to disable it.",
    acct_2fa_disable_btn: "Disable 2FA",
    acct_2fa_deactivated: "2FA disabled",
    acct_logout: "Sign out",

    // ---- Settings page ----
    settings_checking: "Checking...",
    settings_connected: "Connected",
    settings_invalid_key: "Invalid key",
    settings_not_configured: "Not configured",
    settings_connection_error: "Connection error",
    settings_key_valid: "AllDebrid key valid",
    settings_key_invalid: "AllDebrid key invalid",
    settings_alldebrid_saved: "AllDebrid saved",
    settings_downloads_saved: "Download settings saved",
    settings_saving: "Saving...",
    settings_saved: "Saved",
    settings_all_saved: "Settings saved",
    settings_load_error: "Unable to load settings",
    settings_error: "Error",

    // ---- Webhook ----
    webhook_sent: "Webhook sent successfully!",
    webhook_fail: "Failed: ",
    webhook_badge_free: "Free",
    webhook_badge_free_self: "Free (self-hosted)",

    // ---- Webhook presets ----
    webhook_discord_info: "<strong>How to set up:</strong><br>1. Open Discord <em>Server Settings</em><br>2. Go to <em>Integrations</em> &rarr; <em>Webhooks</em><br>3. Click <em>New Webhook</em>, choose the channel<br>4. Copy the webhook URL and paste it here",
    webhook_slack_info: "<strong>How to set up:</strong><br>1. Go to <a href=\"https://api.slack.com/apps\" target=\"_blank\" style=\"color:var(--accent)\">api.slack.com/apps</a><br>2. Create an app &rarr; <em>Incoming Webhooks</em> &rarr; Enable<br>3. <em>Add New Webhook to Workspace</em>, choose the channel<br>4. Copy the webhook URL",
    webhook_telegram_info: "<strong>How to set up:</strong><br>1. Talk to <a href=\"https://t.me/BotFather\" target=\"_blank\" style=\"color:var(--accent)\">@BotFather</a> on Telegram<br>2. Send <code>/newbot</code> and follow the steps to get your <em>token</em><br>3. Get your <em>chat_id</em> via <a href=\"https://t.me/userinfobot\" target=\"_blank\" style=\"color:var(--accent)\">@userinfobot</a><br>4. URL: <code>https://api.telegram.org/bot&lt;TOKEN&gt;/sendMessage</code><br><em>The chat_id is sent automatically in the payload.</em>",
    webhook_gotify_info: "<strong>How to set up:</strong><br>1. Install <a href=\"https://gotify.net\" target=\"_blank\" style=\"color:var(--accent)\">Gotify</a> on your server<br>2. Go to <em>Apps</em> &rarr; <em>Create an application</em><br>3. Copy the app token<br>4. URL: <code>https://your-gotify/message?token=YOUR_TOKEN</code>",
    webhook_ntfy_info: "<strong>How to set up:</strong><br>1. Go to <a href=\"https://ntfy.sh\" target=\"_blank\" style=\"color:var(--accent)\">ntfy.sh</a> (or your own instance)<br>2. Choose a unique topic name<br>3. Subscribe to the topic in the ntfy app (Android/iOS/Web)<br>4. URL: <code>https://ntfy.sh/your-topic</code><br><em>No registration required!</em>",
    webhook_signal_info: "<strong>How to set up (self-hosted via signal-cli-rest-api):</strong><br>1. Deploy the Docker image: <code>docker run -d -p 8080:8080 -v /opt/signal:/home/.local/share/signal-cli bbernhard/signal-cli-rest-api</code><br>2. Register your Signal number via the API (<a href=\"https://github.com/bbernhard/signal-cli-rest-api\" target=\"_blank\" style=\"color:var(--accent)\">see docs</a>)<br>3. Build the URL with your sender and recipient numbers:<br><code>http://signal-api:8080/v2/send?from=%2B33sender&amp;to=%2B33recipient</code><br><em>Replace <strong>+33sender</strong> with your registered number and <strong>+33recipient</strong> with the destination number (URL-encode the +).</em>",

    // ---- Update system ----
    update_checking: "Checking...",
    update_check_btn: "Check for updates",
    update_available: "v{{v}} available",
    update_uptodate: "Up to date",
    update_release_notes: "Release notes v",
    update_updating: "Updating...",
    update_restarting: "Restarting...",
    update_failed: "Failed",
    update_available_toast: "Update available: v",
    update_btn_prefix: "Update to v",

    // ---- Settings login ----
    settings_login_invalid: "Invalid credentials",
    settings_login_server_error: "Server connection error",

    // ---- HTML static text ----
    nav_downloads: "Downloads",
    nav_settings: "Settings",
    page_title: "Download Manager",
    input_links_placeholder: "Paste your download links here (one per line)",
    btn_paste: "Paste",
    btn_add: "Add",
    btn_torrent: "Torrent",
    btn_package: "Package",
    dest_choose: "Choose folder...",
    section_downloads: "Active downloads",
    section_packages: "Packages",
    section_torrents: "Active torrents",
    section_history: "History",
    col_name: "Name",
    col_status: "Status",
    col_progress: "Progress",
    col_speed: "Speed",
    col_size: "Size",
    col_dest: "Destination",
    col_actions: "Actions",
    col_date: "Date",
    btn_clear_history: "Clear",
    btn_pause_all: "Pause all",
    btn_resume_all: "Resume all",
    btn_remove_all: "Remove all",
    torrent_modal_title: "Add a torrent",
    torrent_magnet_label: "Magnet links (one per line)",
    torrent_file_label: ".torrent file",
    torrent_or: "— or —",
    btn_cancel: "Cancel",
    btn_add_torrent: "Add",
    pkg_modal_title: "Create a package",
    pkg_name_label: "Package name",
    pkg_links_label: "Links (one per line)",

    // ---- Settings HTML ----
    settings_title: "Settings — Download Manager",
    settings_alldebrid_title: "AllDebrid",
    settings_alldebrid_enabled: "Enable AllDebrid",
    settings_api_key: "API Key",
    settings_btn_test: "Test",
    settings_btn_save_alldebrid: "Save",
    settings_downloads_title: "Downloads",
    settings_simultaneous: "Simultaneous downloads",
    settings_segments: "Segments per file",
    settings_speed_limit: "Speed limit (KB/s, 0 = unlimited)",
    settings_default_dest: "Default destination",
    settings_btn_save_downloads: "Save",
    settings_webhooks_title: "Webhooks",
    settings_webhook_enabled: "Enable webhooks",
    settings_webhook_format: "Format",
    settings_webhook_url: "Webhook URL",
    settings_webhook_events: "Events",
    settings_webhook_evt_complete: "Download complete",
    settings_webhook_evt_failed: "Download failed",
    settings_webhook_evt_package: "Package complete",
    settings_btn_test_webhook: "Test",
    settings_btn_save_all: "Save all settings",
    settings_update_title: "Updates",
    settings_current_version: "Current version",
    settings_language: "Language",

    // ---- Login HTML ----
    login_title: "Download Manager",
    login_username: "Username",
    login_password: "Password",
    login_otp: "OTP Code",
    login_btn: "Sign in",
    setup_title: "Create admin account",
    setup_subtitle: "First-time setup",
    setup_username: "Username",
    setup_password: "Password",
    setup_password_confirm: "Confirm password",
    setup_btn: "Create account",

    // ---- Placeholder keys ----
    login_username_placeholder: "Username",
    login_password_placeholder: "Password",
    login_otp_placeholder: "6-digit 2FA code",
    login_otp_hint: "Enter the code displayed in your authenticator app",
    setup_username_placeholder: "Username",
    setup_password_placeholder: "Password (min. 6 characters)",
    setup_password_confirm_placeholder: "Confirm password",
    fb_folder_name_placeholder: "Folder name...",
    input_links_placeholder: "Paste your links here, one per line...\nSupported: direct links, Uptobox, 1fichier, and all AllDebrid hosters.",
    settings_api_key_placeholder: "Enter your AllDebrid API key...",

    // ---- Additional UI labels ----
    input_links_label: "Download links",
    btn_torrent_title: "Add a torrent / magnet",
    btn_package_title: "Create a link package",
    btn_paste_title: "Paste from clipboard",
    ctrl_resume: "Resume",
    ctrl_pause: "Pause",
    ctrl_delete: "Delete",
    section_completed: "Completed",
    btn_install: "Install",
    btn_add_package: "Create package",
    settings_not_checked: "Not checked",
    settings_version_label: "Current version:",
    settings_api_key_hint: "Find your key at alldebrid.com &rarr; My account &rarr; API Keys",
    settings_simultaneous_hint: "between 1 and 10",
    settings_segments_hint: "More segments = more speed (like JDownloader). 1 = single connection.",
    settings_segments_range: "between 1 and 8",
    settings_speed_limit_hint: "MB/s (0 = unlimited)",
    settings_webhook_format_generic: "Generic (JSON)",
    settings_btn_save_all: "Save all settings",
    fb_title: "Destination folder",
    fb_new_folder: "New folder",
    fb_create: "Create",
    fb_loading: "Loading...",
    fb_navigate_hint: "Browse and select a folder",
    fb_select_folder: "Select this folder",
    fb_recent_paths: "Recent",
    fb_recent_empty: "No recent paths yet — select a folder to save it here",

    // ---- SMB / Network Shares ----
    smb_title: "SMB / Network Shares",
    smb_subtitle: "Mount network shares (CIFS/SMB) as download destinations. Requires cifs-utils: apt-get install cifs-utils",
    smb_empty: "No shares configured",
    smb_name: "Name",
    smb_name_hint: "Local identifier — sets the mount path: /mnt/smb/&lt;name&gt;",
    smb_name_placeholder: "nas-media",
    smb_host: "Host / IP",
    smb_host_hint: "IP address or hostname of your NAS / server",
    smb_share_name: "Share name",
    smb_share_hint: "The share name visible as \\\\server\\sharename",
    smb_username: "Username",
    smb_username_hint: "Leave empty for guest / anonymous access",
    smb_password: "Password",
    smb_password_hint: "Leave empty if no password required",
    smb_vers: "SMB Version",
    smb_vers_auto: "Auto (recommended)",
    smb_vers_hint: "If mount fails with error(22): Invalid argument, try 3.0 or 2.1",
    smb_domain: "Domain",
    smb_domain_hint: "Windows domain or workgroup (usually not needed for home NAS)",
    smb_auto_mount: "Mount automatically on startup",
    smb_btn_add: "Add share",
    smb_btn_mount: "Mount",
    smb_btn_unmount: "Unmount",
    smb_btn_delete: "Delete",
    smb_mounted: "Mounted",
    smb_unmounted: "Unmounted",
    smb_mount_ok: "Share mounted",
    smb_mount_fail: "Mount failed",
    smb_unmount_ok: "Share unmounted",
    smb_added: "Share added",
    smb_deleted: "Share deleted",
    smb_fields_required: "Name, host and share name are required",
    smb_confirm_delete: "Delete share",
    smb_load_error: "Unable to load SMB shares",
  },

  fr: {
    // ---- Status labels ----
    status_pending: "En attente",
    status_downloading: "En cours",
    status_paused: "En pause",
    status_complete: "Terminé",
    status_error: "Erreur",
    status_failed: "Échoué",
    status_debrid: "Débridage",

    // ---- General ----
    error_prefix: "Erreur : ",
    copy_ok: "Chemin copié !",
    copy_fail: "Impossible de copier",
    paste_ok: "Lien(s) collé(s) !",
    paste_empty: "Presse-papiers vide",
    paste_fail: "Impossible d'accéder au presse-papiers",

    // ---- Stats ----
    stats_files: "{{n}} fichier{{s}}",
    stats_active: "{{n}} actif{{s}}",
    stats_pending: "{{n}} en attente",

    // ---- Packages ----
    pkg_files: "fichiers",
    pkg_status_complete: "Terminé",
    pkg_status_partial: "Partiel",
    pkg_status_active: "En cours",
    pkg_deleted: "Paquet supprimé",
    pkg_name_required: "Donnez un nom au paquet",
    pkg_links_required: "Ajoutez des liens",
    pkg_created: "Paquet « {{name}} » créé avec {{n}} lien(s)",

    // ---- History ----
    history_prev: "Précédent",
    history_next: "Suivant",
    history_confirm_clear: "Vider tout l'historique ?",
    history_cleared: "Historique vidé",
    history_confirm_delete: "Supprimer cette entrée de l'historique ?",
    history_confirm_delete_file: "Supprimer cette entrée ET le fichier du disque ?",
    history_deleted: "Entrée supprimée",
    history_deleted_file: "Entrée et fichier supprimés",

    // ---- Torrent ----
    torrent_nothing: "Collez un lien magnet ou sélectionnez un fichier .torrent",
    torrent_added: "{{n}} torrent(s) ajouté(s)",
    torrent_deleted: "Torrent supprimé",
    torrent_dropzone: "Cliquez ou glissez un fichier .torrent ici",

    // ---- Downloads ----
    links_empty: "Collez au moins un lien.",
    links_added: "{{n}} lien{{s}} ajouté{{s}} à la file.",
    confirm_remove_all: "Supprimer tous les téléchargements en cours ?",
    all_removed: "Tous les téléchargements supprimés",
    btn_pause: "Mettre en pause",
    btn_resume: "Reprendre",
    btn_delete: "Supprimer",
    btn_delete_pkg: "Supprimer le paquet",
    btn_delete_history: "Supprimer de l'historique",
    btn_delete_file: "Supprimer le fichier du disque",

    // ---- Login ----
    login_subtitle: "Connectez-vous pour accéder à l'interface",
    login_invalid: "Identifiants invalides",
    login_otp_step: "Vérification en deux étapes requise",
    login_switch_account: "Changer de compte",
    login_server_error: "Erreur de connexion au serveur",
    setup_username_required: "Nom d'utilisateur requis",
    setup_password_min: "Mot de passe : 6 caractères minimum",
    setup_password_mismatch: "Les mots de passe ne correspondent pas",
    setup_success: "Compte admin créé avec succès !",

    // ---- Date formatting ----
    date_locale: "fr-FR",

    // ---- Torrent status ----
    torrent_status_error: "Erreur",
    torrent_status_processing: "Traitement",

    // ---- File browser ----
    fb_loading: "Chargement...",
    fb_empty: "Aucun sous-dossier",
    fb_error: "Erreur : ",
    fb_folder_required: "Nom du dossier requis",
    fb_folder_created: "Dossier « {{name}} » créé",

    // ---- Account ----
    acct_title: "Mon compte",
    acct_role: "Administrateur",
    acct_change_password: "Changer le mot de passe",
    acct_password_placeholder: "Nouveau mot de passe (min. 6 caractères)",
    acct_password_update: "Mettre à jour",
    acct_password_min: "Mot de passe : 6 caractères minimum",
    acct_password_updated: "Mot de passe mis à jour",
    acct_2fa_title: "Authentification à deux facteurs (2FA)",
    acct_2fa_enabled: "Activée",
    acct_2fa_disabled: "Désactivée",
    acct_2fa_enable_btn: "Activer la 2FA",
    acct_2fa_scan_qr: "Scannez ce QR code avec votre application d'authentification (Google Authenticator, Authy, etc.)",
    acct_2fa_manual_key: "Ou entrez cette clé manuellement :",
    acct_2fa_otp_placeholder: "Code OTP à 6 chiffres",
    acct_2fa_verify: "Vérifier et activer",
    acct_2fa_activated: "2FA activée avec succès !",
    acct_2fa_invalid_code: "Code invalide",
    acct_2fa_enter_code: "Entrez un code à 6 chiffres",
    acct_2fa_disable_hint: "La 2FA est activée. Pour la désactiver, entrez votre code OTP actuel.",
    acct_2fa_disable_btn: "Désactiver la 2FA",
    acct_2fa_deactivated: "2FA désactivée",
    acct_logout: "Se déconnecter",

    // ---- Settings page ----
    settings_checking: "Vérification...",
    settings_connected: "Connecté",
    settings_invalid_key: "Clé invalide",
    settings_not_configured: "Non configuré",
    settings_connection_error: "Erreur de connexion",
    settings_key_valid: "Clé AllDebrid valide",
    settings_key_invalid: "Clé AllDebrid invalide",
    settings_alldebrid_saved: "AllDebrid sauvegardé",
    settings_downloads_saved: "Paramètres téléchargements sauvegardés",
    settings_saving: "Sauvegarde...",
    settings_saved: "Sauvegardé",
    settings_all_saved: "Paramètres sauvegardés",
    settings_load_error: "Impossible de charger les paramètres",
    settings_error: "Erreur",

    // ---- Webhook ----
    webhook_sent: "Webhook envoyé avec succès !",
    webhook_fail: "Échec : ",
    webhook_badge_free: "Gratuit",
    webhook_badge_free_self: "Gratuit (self-hosted)",

    // ---- Webhook presets ----
    webhook_discord_info: "<strong>Comment configurer :</strong><br>1. Ouvrir les <em>Paramètres du serveur</em> Discord<br>2. Aller dans <em>Intégrations</em> &rarr; <em>Webhooks</em><br>3. Cliquer <em>Nouveau webhook</em>, choisir le salon<br>4. Copier l'URL du webhook et la coller ici",
    webhook_slack_info: "<strong>Comment configurer :</strong><br>1. Aller sur <a href=\"https://api.slack.com/apps\" target=\"_blank\" style=\"color:var(--accent)\">api.slack.com/apps</a><br>2. Créer une app &rarr; <em>Incoming Webhooks</em> &rarr; Activer<br>3. <em>Add New Webhook to Workspace</em>, choisir le channel<br>4. Copier l'URL du webhook",
    webhook_telegram_info: "<strong>Comment configurer :</strong><br>1. Parler à <a href=\"https://t.me/BotFather\" target=\"_blank\" style=\"color:var(--accent)\">@BotFather</a> sur Telegram<br>2. Envoyer <code>/newbot</code> et suivre les étapes pour obtenir le <em>token</em><br>3. Obtenir votre <em>chat_id</em> via <a href=\"https://t.me/userinfobot\" target=\"_blank\" style=\"color:var(--accent)\">@userinfobot</a><br>4. URL : <code>https://api.telegram.org/bot&lt;TOKEN&gt;/sendMessage</code><br><em>Le chat_id est envoyé automatiquement dans le payload.</em>",
    webhook_gotify_info: "<strong>Comment configurer :</strong><br>1. Installer <a href=\"https://gotify.net\" target=\"_blank\" style=\"color:var(--accent)\">Gotify</a> sur votre serveur<br>2. Aller dans <em>Apps</em> &rarr; <em>Créer une application</em><br>3. Copier le token de l'app<br>4. URL : <code>https://votre-gotify/message?token=VOTRE_TOKEN</code>",
    webhook_ntfy_info: "<strong>Comment configurer :</strong><br>1. Aller sur <a href=\"https://ntfy.sh\" target=\"_blank\" style=\"color:var(--accent)\">ntfy.sh</a> (ou votre instance)<br>2. Choisir un nom de topic unique<br>3. S'abonner au topic dans l'app ntfy (Android/iOS/Web)<br>4. URL : <code>https://ntfy.sh/votre-topic</code><br><em>Aucune inscription requise !</em>",
    webhook_signal_info: "<strong>Comment configurer (auto-hébergé via signal-cli-rest-api) :</strong><br>1. Déployer l'image Docker : <code>docker run -d -p 8080:8080 -v /opt/signal:/home/.local/share/signal-cli bbernhard/signal-cli-rest-api</code><br>2. Enregistrer votre numéro Signal via l'API (<a href=\"https://github.com/bbernhard/signal-cli-rest-api\" target=\"_blank\" style=\"color:var(--accent)\">voir la doc</a>)<br>3. Construire l'URL avec l'expéditeur et le destinataire :<br><code>http://signal-api:8080/v2/send?from=%2B33expediteur&amp;to=%2B33destinataire</code><br><em>Remplacer <strong>+33expediteur</strong> par votre numéro enregistré et <strong>+33destinataire</strong> par le numéro cible (encoder le + en %2B).</em>",

    // ---- Update system ----
    update_checking: "Vérification...",
    update_check_btn: "Vérifier les mises à jour",
    update_available: "v{{v}} disponible",
    update_uptodate: "À jour",
    update_release_notes: "Notes de version v",
    update_updating: "Mise à jour...",
    update_restarting: "Redémarrage...",
    update_failed: "Échec",
    update_available_toast: "Mise à jour disponible : v",
    update_btn_prefix: "Mettre à jour vers v",

    // ---- Settings login ----
    settings_login_invalid: "Identifiants invalides",
    settings_login_server_error: "Erreur de connexion au serveur",

    // ---- HTML static text ----
    nav_downloads: "Téléchargements",
    nav_settings: "Paramètres",
    page_title: "Download Manager",
    input_links_placeholder: "Collez vos liens de téléchargement ici (un par ligne)",
    btn_paste: "Coller",
    btn_add: "Ajouter",
    btn_torrent: "Torrent",
    btn_package: "Paquet",
    dest_choose: "Choisir le dossier...",
    section_downloads: "Téléchargements actifs",
    section_packages: "Paquets",
    section_torrents: "Torrents actifs",
    section_history: "Historique",
    col_name: "Nom",
    col_status: "Statut",
    col_progress: "Progression",
    col_speed: "Vitesse",
    col_size: "Taille",
    col_dest: "Destination",
    col_actions: "Actions",
    col_date: "Date",
    btn_clear_history: "Vider",
    btn_pause_all: "Tout mettre en pause",
    btn_resume_all: "Tout reprendre",
    btn_remove_all: "Tout supprimer",
    torrent_modal_title: "Ajouter un torrent",
    torrent_magnet_label: "Liens magnet (un par ligne)",
    torrent_file_label: "Fichier .torrent",
    torrent_or: "— ou —",
    btn_cancel: "Annuler",
    btn_add_torrent: "Ajouter",
    pkg_modal_title: "Créer un paquet",
    pkg_name_label: "Nom du paquet",
    pkg_links_label: "Liens (un par ligne)",

    // ---- Settings HTML ----
    settings_title: "Paramètres — Download Manager",
    settings_alldebrid_title: "AllDebrid",
    settings_alldebrid_enabled: "Activer AllDebrid",
    settings_api_key: "Clé API",
    settings_btn_test: "Tester",
    settings_btn_save_alldebrid: "Sauvegarder",
    settings_downloads_title: "Téléchargements",
    settings_simultaneous: "Téléchargements simultanés",
    settings_segments: "Segments par fichier",
    settings_speed_limit: "Limite de vitesse (KB/s, 0 = illimité)",
    settings_default_dest: "Destination par défaut",
    settings_btn_save_downloads: "Sauvegarder",
    settings_webhooks_title: "Webhooks",
    settings_webhook_enabled: "Activer les webhooks",
    settings_webhook_format: "Format",
    settings_webhook_url: "URL du webhook",
    settings_webhook_events: "Événements",
    settings_webhook_evt_complete: "Téléchargement terminé",
    settings_webhook_evt_failed: "Téléchargement échoué",
    settings_webhook_evt_package: "Paquet terminé",
    settings_btn_test_webhook: "Tester",
    settings_btn_save_all: "Sauvegarder tous les paramètres",
    settings_update_title: "Mises à jour",
    settings_current_version: "Version actuelle",
    settings_language: "Langue",

    // ---- Login HTML ----
    login_title: "Download Manager",
    login_username: "Nom d'utilisateur",
    login_password: "Mot de passe",
    login_otp: "Code OTP",
    login_btn: "Se connecter",
    setup_title: "Créer un compte administrateur",
    setup_subtitle: "Première configuration",
    setup_username: "Nom d'utilisateur",
    setup_password: "Mot de passe",
    setup_password_confirm: "Confirmer le mot de passe",
    setup_btn: "Créer le compte",

    // ---- Placeholder keys ----
    login_username_placeholder: "Nom d'utilisateur",
    login_password_placeholder: "Mot de passe",
    login_otp_placeholder: "Code 2FA à 6 chiffres",
    login_otp_hint: "Entrez le code affiché dans votre application d'authentification",
    setup_username_placeholder: "Nom d'utilisateur",
    setup_password_placeholder: "Mot de passe (min. 6 caractères)",
    setup_password_confirm_placeholder: "Confirmer le mot de passe",
    fb_folder_name_placeholder: "Nom du dossier...",
    input_links_placeholder: "Collez vos liens ici, un par ligne...\nCompatible : liens directs, Uptobox, 1fichier, et tous les hébergeurs AllDebrid.",
    settings_api_key_placeholder: "Entrez votre clé API AllDebrid...",

    // ---- Additional UI labels ----
    input_links_label: "Liens à télécharger",
    btn_torrent_title: "Ajouter un torrent / magnet",
    btn_package_title: "Créer un paquet de liens",
    btn_paste_title: "Coller depuis le presse-papiers",
    ctrl_resume: "Reprendre",
    ctrl_pause: "Pause",
    ctrl_delete: "Supprimer",
    section_completed: "Terminés",
    btn_install: "Installer",
    btn_add_package: "Créer le paquet",
    settings_not_checked: "Non vérifié",
    settings_version_label: "Version actuelle :",
    settings_api_key_hint: "Retrouvez votre clé sur alldebrid.com &rarr; Mon compte &rarr; Clés API",
    settings_simultaneous_hint: "entre 1 et 10",
    settings_segments_hint: "Plus de segments = plus de vitesse (comme JDownloader). 1 = connexion unique.",
    settings_segments_range: "entre 1 et 8",
    settings_speed_limit_hint: "Mo/s (0 = illimité)",
    settings_webhook_format_generic: "Générique (JSON)",
    settings_btn_save_all: "Sauvegarder tous les paramètres",
    fb_title: "Dossier de destination",
    fb_new_folder: "Nouveau dossier",
    fb_create: "Créer",
    fb_loading: "Chargement...",
    fb_navigate_hint: "Naviguez et sélectionnez un dossier",
    fb_select_folder: "Sélectionner ce dossier",
    fb_recent_paths: "Récents",
    fb_recent_empty: "Aucun chemin récent — sélectionnez un dossier pour le sauvegarder ici",

    // ---- SMB / Network Shares ----
    smb_title: "Partages réseau SMB",
    smb_subtitle: "Montez des partages réseau (CIFS/SMB) comme destinations de téléchargement. Nécessite cifs-utils : apt-get install cifs-utils",
    smb_empty: "Aucun partage configuré",
    smb_name: "Nom",
    smb_name_hint: "Identifiant local — définit le point de montage : /mnt/smb/&lt;nom&gt;",
    smb_name_placeholder: "nas-media",
    smb_host: "Hôte / IP",
    smb_host_hint: "Adresse IP ou nom d'hôte de votre NAS / serveur",
    smb_share_name: "Nom du partage",
    smb_share_hint: "Nom visible sous \\\\serveur\\nom-du-partage",
    smb_username: "Nom d'utilisateur",
    smb_username_hint: "Laisser vide pour accès invité / anonyme",
    smb_password: "Mot de passe",
    smb_password_hint: "Laisser vide si aucun mot de passe requis",
    smb_vers: "Version SMB",
    smb_vers_auto: "Auto (recommandé)",
    smb_vers_hint: "Si le montage échoue avec error(22): Invalid argument, essayez 3.0 ou 2.1",
    smb_domain: "Domaine",
    smb_domain_hint: "Domaine Windows ou groupe de travail (généralement inutile pour un NAS domestique)",
    smb_auto_mount: "Monter automatiquement au démarrage",
    smb_btn_add: "Ajouter un partage",
    smb_btn_mount: "Monter",
    smb_btn_unmount: "Démonter",
    smb_btn_delete: "Supprimer",
    smb_mounted: "Monté",
    smb_unmounted: "Non monté",
    smb_mount_ok: "Partage monté",
    smb_mount_fail: "Échec du montage",
    smb_unmount_ok: "Partage démonté",
    smb_added: "Partage ajouté",
    smb_deleted: "Partage supprimé",
    smb_fields_required: "Nom, hôte et nom du partage sont requis",
    smb_confirm_delete: "Supprimer le partage",
    smb_load_error: "Impossible de charger les partages SMB",
  },
};

// ---- Translation function ----

function t(key, replacements) {
  const lang = localStorage.getItem("dm_lang") || "en";
  const str = (TRANSLATIONS[lang] && TRANSLATIONS[lang][key]) || TRANSLATIONS["en"][key] || key;
  if (replacements) {
    return str.replace(/\{\{(\w+)\}\}/g, function(_, k) {
      return replacements[k] !== undefined ? replacements[k] : _;
    });
  }
  return str;
}

function getLang() {
  return localStorage.getItem("dm_lang") || "en";
}

function setLanguage(lang) {
  localStorage.setItem("dm_lang", lang);
  location.reload();
}

// ---- Apply translations to DOM elements ----

function applyTranslations() {
  document.querySelectorAll("[data-i18n]").forEach(function(el) {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach(function(el) {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  });
  document.querySelectorAll("[data-i18n-title]").forEach(function(el) {
    el.title = t(el.dataset.i18nTitle);
  });
  // Update <html lang>
  document.documentElement.lang = getLang() === "fr" ? "fr" : "en";
}

document.addEventListener("DOMContentLoaded", applyTranslations);
