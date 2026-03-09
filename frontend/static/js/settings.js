// ============================================================
//  Settings page v2
// ============================================================

// Values now read directly from input fields

const API = {
  token: localStorage.getItem("dm_token") || "",
  _headers() {
    const h = { "Content-Type": "application/json" };
    if (this.token) h["Authorization"] = `Bearer ${this.token}`;
    return h;
  },
  async get(url) {
    const r = await fetch(url, { headers: this._headers() });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  async post(url, body) {
    const r = await fetch(url, { method: "POST", headers: this._headers(), body: JSON.stringify(body) });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  async put(url, body) {
    const r = await fetch(url, { method: "PUT", headers: this._headers(), body: JSON.stringify(body) });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
};

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

    const token = localStorage.getItem("dm_token");
    if (!token) { showSettingsLogin(); return false; }
    API.token = token;

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

    // Show account button if auth is enabled
    if (typeof initAccountButton === "function") initAccountButton();
  } catch {
    showToast("Impossible de charger les paramètres", "error");
  }
}

(async () => {
  const authed = await checkSettingsAuth();
  if (authed) bootSettings();
})();
