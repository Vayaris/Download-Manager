// ============================================================
//  Download Manager — Main Application v3
// ============================================================

// ---- SVG Icons ----

const ICONS = {
  pause:  `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>`,
  play:   `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>`,
  trash:  `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>`,
  copy:   `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`,
  check:  `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`,
  folder: `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`,
};

// ---- API helper ----

const API = {
  token: localStorage.getItem("dm_token") || "",

  _headers() {
    const h = { "Content-Type": "application/json" };
    if (this.token) h["Authorization"] = `Bearer ${this.token}`;
    return h;
  },

  async get(url) {
    const r = await fetch(url, { headers: this._headers() });
    if (r.status === 401) { showLogin(); throw new Error("Unauthorized"); }
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async post(url, body) {
    const r = await fetch(url, { method: "POST", headers: this._headers(), body: JSON.stringify(body) });
    if (r.status === 401) { showLogin(); throw new Error("Unauthorized"); }
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async put(url, body) {
    const r = await fetch(url, { method: "PUT", headers: this._headers(), body: JSON.stringify(body) });
    if (r.status === 401) { showLogin(); throw new Error("Unauthorized"); }
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async del(url) {
    const r = await fetch(url, { method: "DELETE", headers: this._headers() });
    if (r.status === 401) { showLogin(); throw new Error("Unauthorized"); }
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
};

// ---- Formatters ----

function fmtBytes(bytes) {
  if (!bytes || bytes === 0) return "—";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

function fmtSpeed(bps) {
  if (!bps || bps === 0) return "—";
  return fmtBytes(bps) + "/s";
}

function fmtName(item) {
  if (item.name && item.name.trim()) return item.name;
  try {
    const url = new URL(item.url);
    const parts = url.pathname.split("/");
    const last = parts[parts.length - 1];
    return last ? decodeURIComponent(last) : url.hostname;
  } catch {
    return item.url.split("/").pop() || item.url.substring(0, 60);
  }
}

function escHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// ---- Status badge ----

const STATUS_LABELS = {
  pending:     "En attente",
  downloading: "En cours",
  paused:      "En pause",
  complete:    "Terminé",
  error:       "Erreur",
  debrid:      "Débridage",
};

function statusBadge(status) {
  const label = STATUS_LABELS[status] || status;
  return `<span class="badge badge-${status}"><span class="b-dot"></span>${label}</span>`;
}

// ---- Copy to clipboard ----

async function copyToClipboard(text, btnEl) {
  try {
    await navigator.clipboard.writeText(text);
    if (btnEl) {
      btnEl.classList.add("copied");
      const orig = btnEl.innerHTML;
      btnEl.innerHTML = ICONS.check;
      setTimeout(() => {
        btnEl.classList.remove("copied");
        btnEl.innerHTML = orig;
      }, 1800);
    }
    showToast("Chemin copié !", "ok");
  } catch {
    showToast("Impossible de copier", "error");
  }
}

// ---- Paste from clipboard ----

async function pasteFromClipboard() {
  try {
    const text = await navigator.clipboard.readText();
    const textarea = document.getElementById("links-input");
    const current = textarea.value.trim();
    if (current) {
      textarea.value = current + "\n" + text.trim();
    } else {
      textarea.value = text.trim();
    }
    textarea.focus();
    if (text.trim()) {
      showToast("Lien(s) collé(s) !", "ok");
    } else {
      showToast("Presse-papiers vide", "error");
    }
  } catch {
    showToast("Impossible d'accéder au presse-papiers", "error");
  }
}

// ---- Render downloads ----

function renderDownloads(downloads) {
  const tbody = document.getElementById("dl-tbody");

  if (!downloads || downloads.length === 0) {
    tbody.innerHTML = `
      <tr class="empty-row">
        <td colspan="7" class="empty-state">
          <div class="empty-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          </div>
          <div class="empty-title">Aucun téléchargement en cours</div>
          <div class="empty-sub">Collez des liens dans le champ ci-dessus pour commencer</div>
        </td>
      </tr>`;
    updateStats([]);
    return;
  }

  updateStats(downloads);

  const rows = downloads.map((item) => {
    const name  = fmtName(item);
    const pct   = item.progress ? item.progress.toFixed(1) : "0.0";
    const done  = parseInt(item.downloaded || 0);
    const total = parseInt(item.size || 0);
    const dest  = item.destination || "—";

    const fillClass = item.status === "complete"
      ? "complete"
      : item.status === "error"
      ? "error"
      : item.status === "downloading"
      ? "downloading"
      : "";

    let pauseResumeBtn = "";
    if (item.status === "downloading") {
      pauseResumeBtn = `<button class="btn-act act-pause" onclick="pauseDownload('${item.id}')" title="Mettre en pause">${ICONS.pause}</button>`;
    } else if (item.status === "paused" || item.status === "error") {
      pauseResumeBtn = `<button class="btn-act act-resume" onclick="resumeDownload('${item.id}')" title="Reprendre">${ICONS.play}</button>`;
    }

    const progressMeta = item.status === "complete"
      ? `<span class="progress-pct" style="color:var(--green)">100%</span><span class="progress-done">${escHtml(fmtBytes(total))}</span>`
      : item.status === "downloading"
      ? `<span class="progress-pct">${pct}%</span><span class="progress-done">${escHtml(fmtBytes(done))} / ${escHtml(fmtBytes(total))}</span>`
      : `<span class="progress-pct">${pct}%</span><span class="progress-done">${escHtml(fmtBytes(total))}</span>`;

    return `
      <tr>
        <td class="col-name">
          <div class="cell-name">
            <span class="file-name" title="${escHtml(name)}">${escHtml(name)}</span>
            <span class="file-url" title="${escHtml(item.url)}">${escHtml(item.url)}</span>
          </div>
        </td>
        <td class="col-status">${statusBadge(item.status)}</td>
        <td class="col-progress">
          <div class="progress-cell">
            <div class="progress-track">
              <div class="progress-fill ${fillClass}" style="width:${pct}%"></div>
            </div>
            <div class="progress-meta">${progressMeta}</div>
          </div>
        </td>
        <td class="col-speed mono-cell">${escHtml(fmtSpeed(item.speed))}</td>
        <td class="col-size mono-cell">${escHtml(fmtBytes(total))}</td>
        <td class="col-dest">
          <div class="dest-cell">
            <span class="dest-cell-path" title="${escHtml(dest)}">${escHtml(dest)}</span>
            <button class="btn-copy-path" onclick="copyToClipboard('${escHtml(dest)}', this)" title="Copier le chemin">${ICONS.copy}</button>
          </div>
        </td>
        <td class="col-actions">
          <div class="row-actions">
            ${pauseResumeBtn}
            <button class="btn-act act-copy" onclick="copyToClipboard('${escHtml(dest)}', this)" title="Copier le chemin de destination">${ICONS.copy}</button>
            <button class="btn-act act-delete" onclick="removeDownload('${item.id}')" title="Supprimer">${ICONS.trash}</button>
          </div>
        </td>
      </tr>`;
  });

  tbody.innerHTML = rows.join("");
}

// ---- Stats chips ----

function updateStats(downloads) {
  const el = document.getElementById("stats-chips");
  if (!el) return;
  if (!downloads || downloads.length === 0) { el.innerHTML = ""; return; }

  const total  = downloads.length;
  const active = downloads.filter(d => d.status === "downloading").length;
  const done   = downloads.filter(d => d.status === "complete").length;

  el.innerHTML = `
    <div class="stat-chip total"><span class="dot"></span>${total} fichier${total > 1 ? "s" : ""}</div>
    ${active > 0 ? `<div class="stat-chip active"><span class="dot"></span>${active} actif${active > 1 ? "s" : ""}</div>` : ""}
    ${done   > 0 ? `<div class="stat-chip done"><span class="dot"></span>${done} terminé${done > 1 ? "s" : ""}</div>` : ""}
  `;
}

// ---- Actions ----

async function addLinks() {
  const textarea  = document.getElementById("links-input");
  const destInput = document.getElementById("dest-path");
  const rawUrls   = textarea.value.trim();

  if (!rawUrls) { showToast("Collez au moins un lien.", "error"); return; }

  let destination = destInput.value.trim();
  if (!destination) {
    try {
      const cfg = await API.get("/api/settings/");
      destination = cfg.default_destination || "/opt/download-manager/downloads";
    } catch {
      destination = "/opt/download-manager/downloads";
    }
  }

  const urls = rawUrls.split("\n").map(u => u.trim()).filter(Boolean);

  try {
    const result = await API.post("/api/downloads/", { urls, destination });
    textarea.value = "";
    showToast(`${result.added} lien${result.added > 1 ? "s" : ""} ajouté${result.added > 1 ? "s" : ""} à la file.`, "ok");
  } catch (e) {
    showToast("Erreur lors de l'ajout : " + e.message, "error");
  }
}

async function removeDownload(id) {
  try { await API.del(`/api/downloads/${id}`); }
  catch (e) { showToast("Erreur : " + e.message, "error"); }
}

async function pauseDownload(id) {
  try { await API.post(`/api/downloads/${id}/pause`, {}); }
  catch (e) { showToast("Erreur : " + e.message, "error"); }
}

async function resumeDownload(id) {
  try { await API.post(`/api/downloads/${id}/resume`, {}); }
  catch (e) { showToast("Erreur : " + e.message, "error"); }
}

async function bulkAction(action) {
  try { await API.post("/api/downloads/actions", { action }); }
  catch (e) { showToast("Erreur : " + e.message, "error"); }
}

// ---- Auth ----

async function checkAuth() {
  try {
    const status = await fetch("/api/auth/status").then(r => r.json());
    if (!status.auth_enabled) return;
    const token = localStorage.getItem("dm_token");
    if (!token) { showLogin(); return; }
    API.token = token;
    try { await API.get("/api/settings/"); }
    catch { showLogin(); }
  } catch { /* server unreachable */ }
}

function showLogin() {
  document.getElementById("login-modal").classList.remove("hidden");
}

async function doLogin() {
  const username = document.getElementById("login-username").value;
  const password = document.getElementById("login-password").value;
  const errEl    = document.getElementById("login-error");

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
    localStorage.setItem("dm_token", data.token);
    API.token = data.token;
    document.getElementById("login-modal").classList.add("hidden");
    errEl.classList.add("hidden");
    loadInitial();
  } catch {
    errEl.textContent = "Erreur de connexion au serveur";
    errEl.classList.remove("hidden");
  }
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !document.getElementById("login-modal").classList.contains("hidden")) {
    doLogin();
  }
  // Ctrl/Cmd + Enter to submit links
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    const textarea = document.getElementById("links-input");
    if (document.activeElement === textarea) {
      addLinks();
    }
  }
});

// ---- Toast ----

let _toastTimer = null;
function showToast(msg, type = "ok") {
  const el = document.getElementById("toast");
  const icon = type === "ok"
    ? `<svg class="toast-icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`
    : `<svg class="toast-icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;
  el.innerHTML = `${icon}<span>${escHtml(msg)}</span>`;
  el.className = `toast ${type}`;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.add("hidden"), 3500);
}

// ---- Server health ----

async function checkAria2() {
  const dot       = document.getElementById("aria2-status");
  const text      = document.getElementById("server-status-text");
  const badge     = document.getElementById("server-badge");
  try {
    await fetch("/api/settings/");
    dot.className   = "status-dot online";
    text.textContent = "En ligne";
    badge.classList.add("online");
  } catch {
    dot.className   = "status-dot offline";
    text.textContent = "Hors ligne";
    badge.classList.remove("online");
  }
}

// ---- Initial load ----

async function loadInitial() {
  try {
    const [downloads, cfg] = await Promise.all([
      API.get("/api/downloads/"),
      API.get("/api/settings/"),
    ]);
    renderDownloads(downloads);

    const destInput = document.getElementById("dest-path");
    if (!destInput.value && cfg.default_destination) {
      destInput.value = cfg.default_destination;
      document.getElementById("dest-label").textContent = cfg.default_destination;
      document.getElementById("dest-selector").classList.add("selected");
    }
  } catch { /* auth handled elsewhere */ }
}

// ---- Boot ----

(async () => {
  await checkAuth();
  await loadInitial();

  WS.on("downloads_update", data => renderDownloads(data));
  WS.init();

  checkAria2();
  setInterval(checkAria2, 15000);
})();
