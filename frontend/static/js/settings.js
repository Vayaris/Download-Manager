// ============================================================
//  Settings page
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
  const badge   = document.getElementById("alldebrid-status-badge");
  const label   = document.getElementById("alldebrid-status-text");
  badge.className = `conn-badge ${state}`;
  label.textContent = text;
}

async function testAllDebrid() {
  // Save the key first so the backend can use it
  const key = document.getElementById("alldebrid-key").value.trim();
  if (key) {
    try { await API.put("/api/settings/", { alldebrid_api_key: key }); } catch {}
  }

  setAllDebridBadge("checking", "Vérification...");

  try {
    const res = await API.post("/api/settings/test-alldebrid", {});
    if (res.valid) {
      setAllDebridBadge("ok", "Connecté");
      showToast("Clé AllDebrid valide ✓", "ok");
    } else {
      setAllDebridBadge("error", "Clé invalide");
      showToast("Clé AllDebrid invalide", "error");
    }
  } catch (e) {
    setAllDebridBadge("error", "Erreur");
    showToast("Erreur : " + e.message, "error");
  }
}

// Auto-check the key on page load if one is already configured
async function checkAllDebridStatus() {
  const key = document.getElementById("alldebrid-key").value.trim();
  if (!key) {
    setAllDebridBadge("unknown", "Non configuré");
    return;
  }
  setAllDebridBadge("checking", "Vérification...");
  try {
    const res = await API.post("/api/settings/test-alldebrid", {});
    setAllDebridBadge(res.valid ? "ok" : "error", res.valid ? "Connecté" : "Clé invalide");
  } catch {
    setAllDebridBadge("error", "Erreur de connexion");
  }
}

// Save only the AllDebrid section
async function saveAllDebrid() {
  const key     = document.getElementById("alldebrid-key").value.trim();
  const enabled = document.getElementById("alldebrid-enabled").checked;
  try {
    await API.put("/api/settings/", { alldebrid_api_key: key, alldebrid_enabled: enabled });
    showToast("AllDebrid sauvegardé", "ok");
    // Re-check status after save
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
  document.getElementById("auth-fields").classList.toggle("hidden", !enabled);
}

async function saveSettings() {
  const resultEl = document.getElementById("save-result");
  resultEl.textContent = "Sauvegarde...";
  resultEl.className = "inline-result";

  const payload = {
    alldebrid_api_key:      document.getElementById("alldebrid-key").value.trim()     || undefined,
    alldebrid_enabled:      document.getElementById("alldebrid-enabled").checked,
    simultaneous_downloads: simultaneousValue,
    default_destination:    document.getElementById("default-dest").value.trim()       || undefined,
    auth_enabled:           document.getElementById("auth-enabled").checked,
    auth_username:          document.getElementById("auth-username").value.trim()      || undefined,
    auth_password:          document.getElementById("auth-password").value             || undefined,
  };

  Object.keys(payload).forEach((k) => payload[k] === undefined && delete payload[k]);

  try {
    await API.put("/api/settings/", payload);
    resultEl.textContent = "✓ Sauvegardé";
    resultEl.className = "inline-result ok";
    showToast("Paramètres sauvegardés", "ok");
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

    document.getElementById("alldebrid-key").value      = cfg.alldebrid_api_key  || "";
    document.getElementById("alldebrid-enabled").checked = cfg.alldebrid_enabled || false;
    document.getElementById("default-dest").value        = cfg.default_destination || "";
    document.getElementById("auth-enabled").checked      = cfg.auth_enabled       || false;
    document.getElementById("auth-username").value       = cfg.auth_username      || "";

    setSimultaneous(cfg.simultaneous_downloads || 3);
    toggleAuthFields();

    // Auto-check AllDebrid status if a key is already stored
    await checkAllDebridStatus();

  } catch {
    showToast("Impossible de charger les paramètres", "error");
  }
})();
