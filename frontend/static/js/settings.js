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
  setAllDebridBadge("checking", "Verification...");
  try {
    const res = await API.post("/api/settings/test-alldebrid", {});
    if (res.valid) {
      setAllDebridBadge("ok", "Connecte");
      showToast("Cle AllDebrid valide", "ok");
    } else {
      setAllDebridBadge("error", "Cle invalide");
      showToast("Cle AllDebrid invalide", "error");
    }
  } catch (e) {
    setAllDebridBadge("error", "Erreur");
    showToast("Erreur : " + e.message, "error");
  }
}

async function checkAllDebridStatus() {
  const key = document.getElementById("alldebrid-key").value.trim();
  if (!key) { setAllDebridBadge("unknown", "Non configure"); return; }
  setAllDebridBadge("checking", "Verification...");
  try {
    const res = await API.post("/api/settings/test-alldebrid", {});
    setAllDebridBadge(res.valid ? "ok" : "error", res.valid ? "Connecte" : "Cle invalide");
  } catch {
    setAllDebridBadge("error", "Erreur de connexion");
  }
}

async function saveAllDebrid() {
  const key = document.getElementById("alldebrid-key").value.trim();
  const enabled = document.getElementById("alldebrid-enabled").checked;
  try {
    await API.put("/api/settings/", { alldebrid_api_key: key, alldebrid_enabled: enabled });
    showToast("AllDebrid sauvegarde", "ok");
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

function toggleAuthFields() {
  const enabled = document.getElementById("auth-enabled").checked;
  if (enabled) {
    loadUserInfo();
  } else {
    document.getElementById("auth-user-info").classList.add("hidden");
  }
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
      showToast("Webhook envoye avec succes !", "ok");
    } else {
      showToast("Echec : " + res.message, "error");
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

// ---- Auth / User management ----

async function loadUserInfo() {
  try {
    const info = await API.get("/api/auth/user-info");
    const section = document.getElementById("auth-user-info");

    if (info.username === "anonymous") {
      section.classList.add("hidden");
      return;
    }

    section.classList.remove("hidden");
    document.getElementById("auth-current-user").textContent = info.username;

    // OTP status
    const badge = document.getElementById("otp-badge");
    const badgeText = document.getElementById("otp-badge-text");
    const setupSection = document.getElementById("otp-setup-section");
    const disableSection = document.getElementById("otp-disable-section");
    const qrSection = document.getElementById("otp-qr-section");

    qrSection.classList.add("hidden");

    if (info.otp_enabled) {
      badge.className = "conn-badge ok";
      badgeText.textContent = "Active";
      setupSection.classList.add("hidden");
      disableSection.classList.remove("hidden");
    } else {
      badge.className = "conn-badge unknown";
      badgeText.textContent = "Desactive";
      setupSection.classList.remove("hidden");
      disableSection.classList.add("hidden");
    }
  } catch {
    document.getElementById("auth-user-info").classList.add("hidden");
  }
}

async function changePassword() {
  const pw = document.getElementById("auth-new-password").value;
  if (pw.length < 6) { showToast("Mot de passe : 6 caracteres minimum", "error"); return; }
  try {
    await API.post("/api/auth/change-password", { username: "", password: pw });
    showToast("Mot de passe mis a jour", "ok");
    document.getElementById("auth-new-password").value = "";
  } catch (e) {
    showToast("Erreur : " + e.message, "error");
  }
}

async function setupOTP() {
  try {
    const res = await API.post("/api/auth/setup-otp", {});
    // Show QR code
    document.getElementById("otp-qr-container").innerHTML =
      `<img src="data:image/png;base64,${res.qr_code}" alt="QR Code" style="max-width:200px;border-radius:8px;border:2px solid var(--border)">`;
    document.getElementById("otp-secret-display").textContent = res.secret;
    document.getElementById("otp-qr-section").classList.remove("hidden");
    document.getElementById("otp-setup-section").classList.add("hidden");
  } catch (e) {
    showToast("Erreur : " + e.message, "error");
  }
}

async function verifyOTP() {
  const code = document.getElementById("otp-verify-code").value.trim();
  if (code.length !== 6) { showToast("Entrez un code a 6 chiffres", "error"); return; }
  try {
    await API.post("/api/auth/verify-otp", { code });
    showToast("2FA activee avec succes !", "ok");
    document.getElementById("otp-qr-section").classList.add("hidden");
    loadUserInfo();
  } catch (e) {
    let msg = "Code invalide";
    try { msg = JSON.parse(e.message).detail; } catch {}
    showToast(msg, "error");
  }
}

async function disableOTP() {
  const code = document.getElementById("otp-disable-code").value.trim();
  if (code.length !== 6) { showToast("Entrez un code a 6 chiffres", "error"); return; }
  try {
    await API.post("/api/auth/disable-otp", { code });
    showToast("2FA desactivee", "ok");
    document.getElementById("otp-disable-code").value = "";
    loadUserInfo();
  } catch (e) {
    let msg = "Code invalide";
    try { msg = JSON.parse(e.message).detail; } catch {}
    showToast(msg, "error");
  }
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
    auth_enabled: document.getElementById("auth-enabled").checked,
    webhook_enabled: document.getElementById("webhook-enabled").checked,
    webhook_url: document.getElementById("webhook-url").value.trim() || undefined,
    webhook_format: document.getElementById("webhook-format").value,
    webhook_events: events,
  };

  Object.keys(payload).forEach((k) => payload[k] === undefined && delete payload[k]);

  try {
    await API.put("/api/settings/", payload);
    resultEl.textContent = "Sauvegarde";
    resultEl.className = "inline-result ok";
    showToast("Parametres sauvegardes", "ok");
  } catch (e) {
    resultEl.textContent = "Erreur";
    resultEl.className = "inline-result error";
    showToast("Erreur : " + e.message, "error");
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

// ---- Boot ----

(async () => {
  try {
    const cfg = await API.get("/api/settings/");

    document.getElementById("alldebrid-key").value      = cfg.alldebrid_api_key || "";
    document.getElementById("alldebrid-enabled").checked = cfg.alldebrid_enabled || false;
    document.getElementById("default-dest").value        = cfg.default_destination || "";
    document.getElementById("auth-enabled").checked      = cfg.auth_enabled || false;

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

    if (cfg.auth_enabled) {
      loadUserInfo();
    }

    await checkAllDebridStatus();
  } catch {
    showToast("Impossible de charger les parametres", "error");
  }
})();
