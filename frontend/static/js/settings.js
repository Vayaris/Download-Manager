// ============================================================
//  Settings page v2
// ============================================================

let simultaneousValue = 3;

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

function setSimultaneous(val) {
  simultaneousValue = val;
  document.querySelectorAll(".btn-num").forEach((btn) => {
    btn.classList.toggle("active", parseInt(btn.dataset.val) === val);
  });
}

function toggleKeyVisibility() {
  const input = document.getElementById("alldebrid-key");
  input.type = input.type === "password" ? "text" : "password";
}

function toggleWebhookFields() {
  const enabled = document.getElementById("webhook-enabled").checked;
  document.getElementById("webhook-fields").classList.toggle("hidden", !enabled);
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
    simultaneous_downloads: simultaneousValue,
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

let _settingsPendingLogin = {};

async function checkSettingsAuth() {
  try {
    const status = await fetch("/api/auth/status").then(r => r.json());

    // No admin exists — redirect to main page for setup
    if (!status.admin_exists) {
      window.location.href = "/";
      return false;
    }

    const token = localStorage.getItem("dm_token");
    if (!token) { showSettingsLogin(); return false; }
    API.token = token;
    try {
      await API.get("/api/settings/");
      return true;
    } catch {
      showSettingsLogin();
      return false;
    }
  } catch {
    return true; // server unreachable, let it try
  }
}

function showSettingsLogin() {
  document.getElementById("login-modal").classList.remove("hidden");
  document.getElementById("login-form").classList.remove("hidden");
  document.getElementById("otp-form").classList.add("hidden");
}

async function doSettingsLogin() {
  const username = document.getElementById("login-username").value;
  const password = document.getElementById("login-password").value;
  const errEl = document.getElementById("login-error");

  try {
    const resp = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!resp.ok) {
      const data = await resp.json();
      errEl.textContent = data.detail || "Identifiants invalides";
      errEl.classList.remove("hidden");
      return;
    }
    const data = await resp.json();
    if (data.otp_required) {
      _settingsPendingLogin = { username, password };
      document.getElementById("login-form").classList.add("hidden");
      document.getElementById("otp-form").classList.remove("hidden");
      document.getElementById("login-otp").value = "";
      document.getElementById("login-otp").focus();
      return;
    }
    localStorage.setItem("dm_token", data.token);
    API.token = data.token;
    document.getElementById("login-modal").classList.add("hidden");
    bootSettings();
  } catch {
    errEl.textContent = "Erreur de connexion au serveur";
    errEl.classList.remove("hidden");
  }
}

async function doSettingsOtpVerify() {
  const otpCode = document.getElementById("login-otp").value.trim();
  const errEl = document.getElementById("otp-error");
  if (otpCode.length !== 6) { errEl.textContent = "Entrez un code à 6 chiffres"; errEl.classList.remove("hidden"); return; }
  try {
    const resp = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: _settingsPendingLogin.username, password: _settingsPendingLogin.password, otp_code: otpCode }),
    });
    if (!resp.ok) {
      const data = await resp.json();
      errEl.textContent = data.detail || "Code OTP invalide";
      errEl.classList.remove("hidden");
      document.getElementById("login-otp").value = "";
      document.getElementById("login-otp").focus();
      return;
    }
    const data = await resp.json();
    _settingsPendingLogin = {};
    localStorage.setItem("dm_token", data.token);
    API.token = data.token;
    document.getElementById("login-modal").classList.add("hidden");
    bootSettings();
  } catch {
    errEl.textContent = "Erreur de connexion au serveur";
    errEl.classList.remove("hidden");
  }
}

function backToSettingsLogin() {
  _settingsPendingLogin = {};
  document.getElementById("otp-form").classList.add("hidden");
  document.getElementById("login-form").classList.remove("hidden");
  document.getElementById("login-password").value = "";
}

// Enter key support for login
document.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !document.getElementById("login-modal").classList.contains("hidden")) {
    if (!document.getElementById("otp-form").classList.contains("hidden")) {
      doSettingsOtpVerify();
    } else {
      doSettingsLogin();
    }
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

    setSimultaneous(cfg.simultaneous_downloads || 3);

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
