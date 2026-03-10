// ============================================================
//  Settings page v2
// ============================================================

// Values now read directly from input fields

// API helper — delegates to shared apiFetch from api.js
const API = apiFetch;

// ---- AllDebrid connection badge ----

function setAllDebridBadge(state, text) {
  const badge = document.getElementById("alldebrid-status-badge");
  const label = document.getElementById("alldebrid-status-text");
  badge.className = `conn-badge ${state}`;
  label.textContent = text;
}

async function testAllDebrid() {
  const key = document.getElementById("alldebrid-key").value.trim();
  if (key) {
    try { await API.put("/api/settings/", { alldebrid_api_key: key }); } catch {}
  }
  setAllDebridBadge("checking", "Vérification...");
  try {
    const res = await API.post("/api/settings/test-alldebrid", {});
    if (res.valid) {
      setAllDebridBadge("ok", "Connecté");
      showToast("Clé AllDebrid valide", "ok");
      // Auto-enable when key is valid
      document.getElementById("alldebrid-enabled").checked = true;
      await API.put("/api/settings/", { alldebrid_enabled: true });
    } else {
      setAllDebridBadge("error", "Clé invalide");
      showToast("Clé AllDebrid invalide", "error");
    }
  } catch (e) {
    setAllDebridBadge("error", "Erreur");
    showToast("Erreur : " + e.message, "error");
  }
}

async function checkAllDebridStatus() {
  const key = document.getElementById("alldebrid-key").value.trim();
  if (!key) { setAllDebridBadge("unknown", "Non configuré"); return; }
  setAllDebridBadge("checking", "Vérification...");
  try {
    const res = await API.post("/api/settings/test-alldebrid", {});
    setAllDebridBadge(res.valid ? "ok" : "error", res.valid ? "Connecté" : "Clé invalide");
  } catch {
    setAllDebridBadge("error", "Erreur de connexion");
  }
}

async function saveAllDebrid() {
  const key = document.getElementById("alldebrid-key").value.trim();
  const enabled = document.getElementById("alldebrid-enabled").checked;
  try {
    await API.put("/api/settings/", { alldebrid_api_key: key, alldebrid_enabled: enabled });
    showToast("AllDebrid sauvegardé", "ok");
    await checkAllDebridStatus();
  } catch (e) {
    showToast("Erreur : " + e.message, "error");
  }
}

// ---- Other settings ----

async function saveDownloadSettings() {
  const simultaneous = Math.min(10, Math.max(1, parseInt(document.getElementById("simultaneous-input").value) || 3));
  const segments = Math.min(8, Math.max(1, parseInt(document.getElementById("segments-input").value) || 1));
  const speedLimit = parseInt(document.getElementById("speed-limit").value) || 0;
  const dest = document.getElementById("default-dest").value.trim() || undefined;

  // Clamp input values visually
  document.getElementById("simultaneous-input").value = simultaneous;
  document.getElementById("segments-input").value = segments;

  try {
    await API.put("/api/settings/", {
      simultaneous_downloads: simultaneous,
      download_segments: segments,
      speed_limit: speedLimit,
      default_destination: dest,
    });
    showToast("Paramètres téléchargements sauvegardés", "ok");
  } catch (e) {
    showToast("Erreur : " + e.message, "error");
  }
}

function toggleKeyVisibility() {
  const input = document.getElementById("alldebrid-key");
  input.type = input.type === "password" ? "text" : "password";
}

function toggleWebhookFields() {
  const enabled = document.getElementById("webhook-enabled").checked;
  document.getElementById("webhook-fields").classList.toggle("hidden", !enabled);
  if (enabled) updateWebhookPreset();
}

const WEBHOOK_PRESETS = {
  generic: {
    placeholder: "https://example.com/webhook",
    badge: null,
    info: null,
  },
  discord: {
    placeholder: "https://discord.com/api/webhooks/...",
    badge: "Gratuit",
    info: `<strong>Comment configurer :</strong><br>
1. Ouvrir les <em>Paramètres du serveur</em> Discord<br>
2. Aller dans <em>Intégrations</em> &rarr; <em>Webhooks</em><br>
3. Cliquer <em>Nouveau webhook</em>, choisir le salon<br>
4. Copier l'URL du webhook et la coller ici`,
  },
  slack: {
    placeholder: "https://hooks.slack.com/services/T.../B.../...",
    badge: "Gratuit",
    info: `<strong>Comment configurer :</strong><br>
1. Aller sur <a href="https://api.slack.com/apps" target="_blank" style="color:var(--accent)">api.slack.com/apps</a><br>
2. Créer une app &rarr; <em>Incoming Webhooks</em> &rarr; Activer<br>
3. <em>Add New Webhook to Workspace</em>, choisir le channel<br>
4. Copier l'URL du webhook`,
  },
  telegram: {
    placeholder: "https://api.telegram.org/bot<TOKEN>/sendMessage",
    badge: "Gratuit",
    info: `<strong>Comment configurer :</strong><br>
1. Parler à <a href="https://t.me/BotFather" target="_blank" style="color:var(--accent)">@BotFather</a> sur Telegram<br>
2. Envoyer <code>/newbot</code> et suivre les étapes pour obtenir le <em>token</em><br>
3. Obtenir votre <em>chat_id</em> via <a href="https://t.me/userinfobot" target="_blank" style="color:var(--accent)">@userinfobot</a><br>
4. URL : <code>https://api.telegram.org/bot&lt;TOKEN&gt;/sendMessage</code><br>
<em>Le chat_id est envoyé automatiquement dans le payload.</em>`,
  },
  gotify: {
    placeholder: "https://gotify.example.com/message?token=...",
    badge: "Gratuit (self-hosted)",
    info: `<strong>Comment configurer :</strong><br>
1. Installer <a href="https://gotify.net" target="_blank" style="color:var(--accent)">Gotify</a> sur votre serveur<br>
2. Aller dans <em>Apps</em> &rarr; <em>Créer une application</em><br>
3. Copier le token de l'app<br>
4. URL : <code>https://votre-gotify/message?token=VOTRE_TOKEN</code>`,
  },
  ntfy: {
    placeholder: "https://ntfy.sh/votre-topic",
    badge: "Gratuit",
    info: `<strong>Comment configurer :</strong><br>
1. Aller sur <a href="https://ntfy.sh" target="_blank" style="color:var(--accent)">ntfy.sh</a> (ou votre instance)<br>
2. Choisir un nom de topic unique<br>
3. S'abonner au topic dans l'app ntfy (Android/iOS/Web)<br>
4. URL : <code>https://ntfy.sh/votre-topic</code><br>
<em>Aucune inscription requise !</em>`,
  },
};

function updateWebhookPreset() {
  const format = document.getElementById("webhook-format").value;
  const preset = WEBHOOK_PRESETS[format];
  const urlInput = document.getElementById("webhook-url");
  const infoDiv = document.getElementById("webhook-preset-info");

  if (preset && preset.placeholder) {
    urlInput.placeholder = preset.placeholder;
  }

  if (!preset || !preset.info) {
    infoDiv.classList.add("hidden");
    return;
  }

  infoDiv.classList.remove("hidden");
  infoDiv.innerHTML = `
    <div class="preset-header">
      ${preset.badge ? `<span class="preset-badge">${preset.badge}</span>` : ""}
    </div>
    <div class="preset-guide">${preset.info}</div>`;
}

// ---- Webhook test ----

async function testWebhook() {
  try {
    // Save webhook settings first
    await saveWebhookSettings();
    const res = await API.post("/api/settings/test-webhook", {});
    if (res.success) {
      showToast("Webhook envoyé avec succès !", "ok");
    } else {
      showToast("Échec : " + res.message, "error");
    }
  } catch (e) {
    showToast("Erreur : " + e.message, "error");
  }
}

async function saveWebhookSettings() {
  const events = [];
  if (document.getElementById("wh-evt-complete").checked) events.push("download_complete");
  if (document.getElementById("wh-evt-failed").checked) events.push("download_failed");
  if (document.getElementById("wh-evt-package").checked) events.push("package_complete");

  await API.put("/api/settings/", {
    webhook_enabled: document.getElementById("webhook-enabled").checked,
    webhook_url: document.getElementById("webhook-url").value.trim(),
    webhook_format: document.getElementById("webhook-format").value,
    webhook_events: events,
  });
}

// ---- Save all settings ----

async function saveSettings() {
  const resultEl = document.getElementById("save-result");
  resultEl.textContent = "Sauvegarde...";
  resultEl.className = "inline-result";

  // Collect webhook events
  const events = [];
  if (document.getElementById("wh-evt-complete").checked) events.push("download_complete");
  if (document.getElementById("wh-evt-failed").checked) events.push("download_failed");
  if (document.getElementById("wh-evt-package").checked) events.push("package_complete");

  const payload = {
    alldebrid_api_key: document.getElementById("alldebrid-key").value.trim() || undefined,
    alldebrid_enabled: document.getElementById("alldebrid-enabled").checked,
    simultaneous_downloads: Math.min(10, Math.max(1, parseInt(document.getElementById("simultaneous-input").value) || 3)),
    download_segments: Math.min(8, Math.max(1, parseInt(document.getElementById("segments-input").value) || 1)),
    speed_limit: parseInt(document.getElementById("speed-limit").value) || 0,
    default_destination: document.getElementById("default-dest").value.trim() || undefined,
    webhook_enabled: document.getElementById("webhook-enabled").checked,
    webhook_url: document.getElementById("webhook-url").value.trim() || undefined,
    webhook_format: document.getElementById("webhook-format").value,
    webhook_events: events,
  };

  Object.keys(payload).forEach((k) => payload[k] === undefined && delete payload[k]);

  try {
    await API.put("/api/settings/", payload);
    resultEl.textContent = "Sauvegardé";
    resultEl.className = "inline-result ok";
    showToast("Paramètres sauvegardés", "ok");
  } catch (e) {
    resultEl.textContent = "Erreur";
    resultEl.className = "inline-result error";
    let msg = e.message;
    try { msg = JSON.parse(e.message).detail; } catch {}
    showToast("Erreur : " + msg, "error");
  }
}

// ---- Toast ----

let _toastTimer = null;
function showToast(msg, type = "ok") {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className = `toast ${type}`;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.add("hidden"), 3500);
}

// ---- Auth check for settings page ----

async function checkSettingsAuth() {
  try {
    const status = await fetch("/api/auth/status").then(r => r.json());

    if (!status.admin_exists) {
      window.location.href = "/";
      return false;
    }

    const token = getAuthToken();
    if (!token) { showSettingsLogin(); return false; }

    // Validate token with raw fetch
    const check = await fetch("/api/settings/", {
      headers: { "Authorization": `Bearer ${token}` },
    });
    if (check.status === 401) {
      localStorage.removeItem("dm_token");
      API.token = "";
      showSettingsLogin();
      return false;
    }
    return true;
  } catch {
    return true;
  }
}

function showSettingsLogin() {
  document.getElementById("login-modal").classList.remove("hidden");
  document.getElementById("login-form").classList.remove("hidden");
  document.getElementById("otp-group").classList.add("hidden");
  document.getElementById("login-otp").value = "";
  document.getElementById("login-error").classList.add("hidden");
}

let _settingsOtpRequired = false;

async function doSettingsLogin() {
  const username = document.getElementById("login-username").value;
  const password = document.getElementById("login-password").value;
  const otpCode  = document.getElementById("login-otp").value.trim();
  const errEl    = document.getElementById("login-error");

  errEl.classList.add("hidden");

  const body = { username, password };
  if (_settingsOtpRequired && otpCode) {
    body.otp_code = otpCode;
  }

  try {
    const resp = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      const data = await resp.json();
      errEl.textContent = data.detail || "Identifiants invalides";
      errEl.classList.remove("hidden");
      if (_settingsOtpRequired) {
        document.getElementById("login-otp").value = "";
        document.getElementById("login-otp").focus();
      }
      return;
    }
    const data = await resp.json();

    if (data.otp_required) {
      _settingsOtpRequired = true;
      document.getElementById("otp-group").classList.remove("hidden");
      document.getElementById("login-otp").value = "";
      document.getElementById("login-otp").focus();
      return;
    }

    _settingsOtpRequired = false;
    localStorage.setItem("dm_token", data.token);
    API.token = data.token;
    document.getElementById("login-modal").classList.add("hidden");
    bootSettings();
  } catch {
    errEl.textContent = "Erreur de connexion au serveur";
    errEl.classList.remove("hidden");
  }
}

// Enter key support for login
document.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !document.getElementById("login-modal").classList.contains("hidden")) {
    doSettingsLogin();
  }
});

// ---- Boot ----

async function bootSettings() {
  try {
    const cfg = await API.get("/api/settings/");

    document.getElementById("alldebrid-key").value      = cfg.alldebrid_api_key || "";
    document.getElementById("alldebrid-enabled").checked = cfg.alldebrid_enabled || false;
    document.getElementById("default-dest").value        = cfg.default_destination || "";
    // Webhooks
    document.getElementById("webhook-enabled").checked = cfg.webhook_enabled || false;
    document.getElementById("webhook-url").value = cfg.webhook_url || "";
    document.getElementById("webhook-format").value = cfg.webhook_format || "generic";
    if (cfg.webhook_events) {
      document.getElementById("wh-evt-complete").checked = cfg.webhook_events.includes("download_complete");
      document.getElementById("wh-evt-failed").checked = cfg.webhook_events.includes("download_failed");
      document.getElementById("wh-evt-package").checked = cfg.webhook_events.includes("package_complete");
    }
    toggleWebhookFields();

    document.getElementById("simultaneous-input").value = cfg.simultaneous_downloads || 3;
    document.getElementById("segments-input").value = cfg.download_segments || 1;
    document.getElementById("speed-limit").value = cfg.speed_limit || 0;

    await checkAllDebridStatus();

    // Load current version
    try {
      const ver = await API.get("/api/settings/version");
      document.getElementById("current-version").textContent = "v" + ver.version;
    } catch {}

    // Show account button if auth is enabled
    if (typeof initAccountButton === "function") initAccountButton();
  } catch {
    showToast("Impossible de charger les paramètres", "error");
  }
}

// ---- Update system ----

function setUpdateBadge(state, text) {
  const badge = document.getElementById("update-badge");
  const label = document.getElementById("update-badge-text");
  badge.className = `conn-badge ${state}`;
  label.textContent = text;
}

function renderChangelog(md) {
  // Simple markdown → HTML (headers, bold, lists, line breaks)
  if (!md) return "";
  return md
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/^### (.+)$/gm, '<h4 style="margin:8px 0 4px;font-size:13px;color:var(--text)">$1</h4>')
    .replace(/^## (.+)$/gm, '<h3 style="margin:10px 0 6px;font-size:14px;color:var(--text)">$1</h3>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^- (.+)$/gm, '<div style="padding-left:12px;position:relative"><span style="position:absolute;left:0">•</span> $1</div>')
    .replace(/\n\n/g, '<br>')
    .replace(/`([^`]+)`/g, '<code style="background:var(--surface-3);padding:1px 5px;border-radius:3px;font-size:12px">$1</code>');
}

async function checkForUpdate() {
  const btn = document.getElementById("btn-check-update");
  btn.disabled = true;
  btn.textContent = "Vérification...";
  setUpdateBadge("checking", "Vérification...");

  try {
    const res = await API.get("/api/settings/check-update");
    document.getElementById("current-version").textContent = "v" + res.current;

    if (res.update_available) {
      setUpdateBadge("error", `v${res.latest} disponible`);
      document.getElementById("btn-do-update").classList.remove("hidden");
      document.getElementById("btn-do-update").textContent = `Mettre à jour vers v${res.latest}`;

      // Show changelog
      if (res.changelog) {
        document.getElementById("update-info").classList.remove("hidden");
        document.getElementById("update-changelog").innerHTML =
          '<p style="font-size:12px;color:var(--text-3);margin-bottom:6px;font-weight:600;text-transform:uppercase;letter-spacing:.5px">Notes de version v' + escHtml(res.latest) + '</p>' +
          '<div style="font-size:13px;color:var(--text-2);line-height:1.5">' + renderChangelog(res.changelog) + '</div>';
      }
      showToast("Mise à jour disponible : v" + res.latest, "ok");
    } else {
      setUpdateBadge("ok", "À jour");
      document.getElementById("btn-do-update").classList.add("hidden");
      document.getElementById("update-info").classList.add("hidden");
      showToast(res.message || "Vous êtes à jour", "ok");
    }
  } catch (e) {
    setUpdateBadge("error", "Erreur");
    showToast("Erreur : " + e.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Vérifier les mises à jour";
  }
}

async function performUpdate() {
  const btn = document.getElementById("btn-do-update");
  btn.disabled = true;
  const origText = btn.textContent;
  btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="animation:spin 1s linear infinite"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg> Mise à jour en cours...';
  setUpdateBadge("checking", "Mise à jour...");

  try {
    const res = await API.post("/api/settings/update", {});
    if (res.success) {
      setUpdateBadge("ok", "v" + res.version);
      showToast(res.message, "ok");
      btn.textContent = "Redémarrage...";

      // Wait for the service to restart, then reload
      setTimeout(() => {
        const poll = setInterval(async () => {
          try {
            const r = await fetch("/api/settings/version", {
              headers: API._headers(),
            });
            if (r.ok) {
              clearInterval(poll);
              window.location.reload();
            }
          } catch {}
        }, 1500);
        // Stop polling after 30s
        setTimeout(() => clearInterval(poll), 30000);
      }, 2000);
    } else {
      setUpdateBadge("error", "Échec");
      showToast(res.message || "Mise à jour échouée", "error");
      btn.disabled = false;
      btn.textContent = origText;
    }
  } catch (e) {
    setUpdateBadge("error", "Échec");
    showToast("Erreur : " + e.message, "error");
    btn.disabled = false;
    btn.textContent = origText;
  }
}

// ---- Boot ----

(async () => {
  const authed = await checkSettingsAuth();
  if (authed) bootSettings();
})();
