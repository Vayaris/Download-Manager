// ============================================================
//  Download Manager — Main Application v4
// ============================================================

// ---- SVG Icons ----

const ICONS = {
  pause:  `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>`,
  play:   `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>`,
  trash:  `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>`,
  copy:   `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`,
  check:  `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`,
  folder: `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`,
  chevDown: `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>`,
  chevRight: `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>`,
  pkg: `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16.5 9.4 7.55 4.24"/><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.29 7 12 12 20.71 7"/><line x1="12" y1="22" x2="12" y2="12"/></svg>`,
  retry: `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>`,
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
  if (!bytes || bytes === 0) return "\u2014";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

function fmtSpeed(bps) {
  if (!bps || bps === 0) return "\u2014";
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

function fmtDate(iso) {
  if (!iso) return "\u2014";
  const d = new Date(iso + "Z");
  return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "2-digit" })
    + " " + d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
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
  failed:      "Échoué",
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
      setTimeout(() => { btnEl.classList.remove("copied"); btnEl.innerHTML = orig; }, 1800);
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
    textarea.value = current ? current + "\n" + text.trim() : text.trim();
    textarea.focus();
    showToast(text.trim() ? "Lien(s) collé(s) !" : "Presse-papiers vide", text.trim() ? "ok" : "error");
  } catch {
    showToast("Impossible d'accéder au presse-papiers", "error");
  }
}

// ---- Render downloads ----

function renderDownloads(downloads) {
  const tbody = document.getElementById("dl-tbody");

  // Filter out downloads that belong to packages (they're shown in package view)
  const standalone = downloads.filter(d => !d.package_id);

  if (!standalone || standalone.length === 0) {
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
    updateStats(downloads);
    return;
  }

  updateStats(downloads);
  tbody.innerHTML = standalone.map(item => renderDownloadRow(item)).join("");
}

function renderDownloadRow(item) {
  const name  = fmtName(item);
  const pct   = item.progress ? item.progress.toFixed(1) : "0.0";
  const done  = parseInt(item.downloaded || 0);
  const total = parseInt(item.size || 0);
  const dest  = item.destination || "\u2014";

  const fillClass = item.status === "complete" ? "complete"
    : item.status === "error" || item.status === "failed" ? "error"
    : item.status === "downloading" ? "downloading" : "";

  let pauseResumeBtn = "";
  if (item.status === "downloading") {
    pauseResumeBtn = `<button class="btn-act act-pause" onclick="pauseDownload('${item.id}')" title="Mettre en pause">${ICONS.pause}</button>`;
  } else if (item.status === "paused" || item.status === "error" || item.status === "failed") {
    pauseResumeBtn = `<button class="btn-act act-resume" onclick="resumeDownload('${item.id}')" title="Reprendre">${ICONS.play}</button>`;
  }

  // Retry info
  let retryInfo = "";
  if (item.retry_count > 0 && item.status !== "complete") {
    retryInfo = `<span class="retry-badge" title="${escHtml(item.error_msg || '')}">${ICONS.retry} ${item.retry_count}/${item.max_retries || 5}</span>`;
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
          ${retryInfo}
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
        </div>
      </td>
      <td class="col-actions">
        <div class="row-actions">
          ${pauseResumeBtn}
          <button class="btn-act act-delete" onclick="removeDownload('${item.id}')" title="Supprimer">${ICONS.trash}</button>
        </div>
      </td>
    </tr>`;
}

// ---- Packages rendering ----

let expandedPackages = new Set();

function renderPackages(packages) {
  const section = document.getElementById("packages-section");
  const list = document.getElementById("packages-list");

  if (!packages || packages.length === 0) {
    section.classList.add("hidden");
    return;
  }

  section.classList.remove("hidden");

  list.innerHTML = packages.map(pkg => {
    const isExpanded = expandedPackages.has(pkg.id);
    const pct = pkg.progress ? pkg.progress.toFixed(1) : "0.0";
    const totalSpeed = (pkg.downloads || []).reduce((s, d) => s + (d.speed || 0), 0);

    const statusClass = pkg.status === "complete" ? "complete"
      : pkg.status === "partial" ? "error"
      : "downloading";

    const pkgStatusLabel = pkg.status === "complete" ? "Terminé"
      : pkg.status === "partial" ? "Partiel"
      : "En cours";

    let downloadsHtml = "";
    if (isExpanded && pkg.downloads) {
      downloadsHtml = `<div class="pkg-downloads">
        <table class="dl-table pkg-table">
          <tbody>${pkg.downloads.map(d => renderDownloadRow(d)).join("")}</tbody>
        </table>
      </div>`;
    }

    return `
      <div class="pkg-card">
        <div class="pkg-header" onclick="togglePackage('${pkg.id}')">
          <div class="pkg-chevron">${isExpanded ? ICONS.chevDown : ICONS.chevRight}</div>
          <div class="pkg-icon">${ICONS.pkg}</div>
          <div class="pkg-info">
            <span class="pkg-name">${escHtml(pkg.name)}</span>
            <span class="pkg-meta">${pkg.completed_files || 0}/${pkg.total_files || 0} fichiers \u2022 ${escHtml(fmtBytes(pkg.total_size))}</span>
          </div>
          <div class="pkg-progress-wrap">
            <div class="progress-track" style="width:120px">
              <div class="progress-fill ${statusClass}" style="width:${pct}%"></div>
            </div>
            <span class="progress-pct">${pct}%</span>
          </div>
          <span class="badge badge-${statusClass}" style="margin-left:8px"><span class="b-dot"></span>${pkgStatusLabel}</span>
          ${totalSpeed > 0 ? `<span class="pkg-speed mono-cell">${escHtml(fmtSpeed(totalSpeed))}</span>` : ''}
          <button class="btn-act act-delete" onclick="event.stopPropagation();removePackage('${pkg.id}')" title="Supprimer le paquet">${ICONS.trash}</button>
        </div>
        ${downloadsHtml}
      </div>`;
  }).join("");
}

function togglePackage(id) {
  if (expandedPackages.has(id)) {
    expandedPackages.delete(id);
  } else {
    expandedPackages.add(id);
  }
  loadPackages();
}

async function loadPackages() {
  try {
    const packages = await API.get("/api/downloads/packages");
    renderPackages(packages);
  } catch {}
}

async function removePackage(id) {
  try {
    await API.del(`/api/downloads/packages/${id}`);
    expandedPackages.delete(id);
    showToast("Paquet supprimé", "ok");
  } catch (e) { showToast("Erreur : " + e.message, "error"); }
}

// ---- Package modal ----

let _pkgFileBrowserMode = false;

function openPackageModal() {
  document.getElementById("package-modal").classList.remove("hidden");
  const mainDest = document.getElementById("dest-path").value;
  if (mainDest) {
    document.getElementById("pkg-dest-path").value = mainDest;
    document.getElementById("pkg-dest-label").textContent = mainDest;
    document.getElementById("pkg-dest-selector").classList.add("selected");
  }
}
function closePackageModal() {
  document.getElementById("package-modal").classList.add("hidden");
}

function openFileBrowserForPackage() {
  _pkgFileBrowserMode = true;
  FileBrowser.open((path) => {
    document.getElementById("pkg-dest-path").value = path;
    document.getElementById("pkg-dest-label").textContent = path;
    document.getElementById("pkg-dest-selector").classList.add("selected");
    _pkgFileBrowserMode = false;
  });
}

async function addPackage() {
  const name = document.getElementById("pkg-name").value.trim();
  const links = document.getElementById("pkg-links").value.trim();
  const dest = document.getElementById("pkg-dest-path").value.trim();

  if (!name) { showToast("Donnez un nom au paquet", "error"); return; }
  if (!links) { showToast("Ajoutez des liens", "error"); return; }

  let destination = dest;
  if (!destination) {
    try {
      const cfg = await API.get("/api/settings/");
      destination = cfg.default_destination || "/opt/download-manager/downloads";
    } catch {
      destination = "/opt/download-manager/downloads";
    }
  }

  const urls = links.split("\n").map(u => u.trim()).filter(Boolean);

  try {
    const result = await API.post("/api/downloads/packages", { name, urls, destination });
    showToast(`Paquet « ${name} » créé avec ${result.added} lien(s)`, "ok");
    document.getElementById("pkg-name").value = "";
    document.getElementById("pkg-links").value = "";
    closePackageModal();
    loadPackages();
  } catch (e) {
    showToast("Erreur : " + e.message, "error");
  }
}

// ---- Stats chips ----

function updateStats(downloads) {
  const el = document.getElementById("stats-chips");
  if (!el) return;
  if (!downloads || downloads.length === 0) { el.innerHTML = ""; return; }

  const total  = downloads.length;
  const active = downloads.filter(d => d.status === "downloading").length;
  const done   = downloads.filter(d => d.status === "complete").length;
  const failed = downloads.filter(d => d.status === "failed").length;

  el.innerHTML = `
    <div class="stat-chip total"><span class="dot"></span>${total} fichier${total > 1 ? "s" : ""}</div>
    ${active > 0 ? `<div class="stat-chip active"><span class="dot"></span>${active} actif${active > 1 ? "s" : ""}</div>` : ""}
    ${done   > 0 ? `<div class="stat-chip done"><span class="dot"></span>${done} terminé${done > 1 ? "s" : ""}</div>` : ""}
    ${failed > 0 ? `<div class="stat-chip failed"><span class="dot"></span>${failed} échoué${failed > 1 ? "s" : ""}</div>` : ""}
  `;
}

// ---- History ----

let historyPage = 0;
const HISTORY_PER_PAGE = 20;

async function loadHistory() {
  try {
    const data = await API.get(`/api/downloads/history?limit=${HISTORY_PER_PAGE}&offset=${historyPage * HISTORY_PER_PAGE}`);
    const section = document.getElementById("history-section");
    const tbody = document.getElementById("history-tbody");
    const pagination = document.getElementById("history-pagination");

    if (data.total === 0) {
      section.classList.add("hidden");
      return;
    }

    section.classList.remove("hidden");

    tbody.innerHTML = data.items.map(item => `
      <tr>
        <td class="col-name">
          <div class="cell-name">
            <span class="file-name" title="${escHtml(item.name)}">${escHtml(item.name || item.url)}</span>
            ${item.package_name ? `<span class="file-url">${ICONS.pkg} ${escHtml(item.package_name)}</span>` : `<span class="file-url" title="${escHtml(item.url)}">${escHtml(item.url)}</span>`}
          </div>
        </td>
        <td class="col-status">${statusBadge(item.status)}</td>
        <td class="col-size mono-cell">${escHtml(fmtBytes(item.size))}</td>
        <td class="col-dest">
          <span class="dest-cell-path" title="${escHtml(item.destination)}">${escHtml(item.destination)}</span>
        </td>
        <td class="mono-cell" style="font-size:11px">${fmtDate(item.completed_at)}</td>
      </tr>
    `).join("");

    const totalPages = Math.ceil(data.total / HISTORY_PER_PAGE);
    if (totalPages > 1) {
      let paginationHtml = "";
      if (historyPage > 0) {
        paginationHtml += `<button class="btn btn-sm" onclick="historyPage--;loadHistory()">Précédent</button>`;
      }
      paginationHtml += `<span class="pagination-info">${historyPage + 1} / ${totalPages}</span>`;
      if (historyPage < totalPages - 1) {
        paginationHtml += `<button class="btn btn-sm" onclick="historyPage++;loadHistory()">Suivant</button>`;
      }
      pagination.innerHTML = paginationHtml;
    } else {
      pagination.innerHTML = "";
    }
  } catch {}
}

async function clearHistory() {
  try {
    await API.del("/api/downloads/history");
    historyPage = 0;
    loadHistory();
    showToast("Historique vidé", "ok");
  } catch (e) { showToast("Erreur : " + e.message, "error"); }
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
  try {
    await API.post("/api/downloads/actions", { action });
    if (action === "clear_completed") {
      loadHistory();
    }
  }
  catch (e) { showToast("Erreur : " + e.message, "error"); }
}

// ---- Auth ----

async function checkAuth() {
  try {
    const status = await fetch("/api/auth/status").then(r => r.json());
    if (!status.auth_enabled) return;

    // Auth is enabled but no admin exists — show setup form
    if (!status.admin_exists) {
      showSetupForm();
      return;
    }

    const token = localStorage.getItem("dm_token");
    if (!token) { showLogin(); return; }
    API.token = token;
    try { await API.get("/api/settings/"); }
    catch { showLogin(); }
  } catch { /* server unreachable */ }
}

function showLogin() {
  const modal = document.getElementById("login-modal");
  modal.classList.remove("hidden");
  document.getElementById("login-form").classList.remove("hidden");
  document.getElementById("otp-form").classList.add("hidden");
  document.getElementById("setup-form").classList.add("hidden");
}

function showSetupForm() {
  const modal = document.getElementById("login-modal");
  modal.classList.remove("hidden");
  document.getElementById("login-form").classList.add("hidden");
  document.getElementById("setup-form").classList.remove("hidden");
}

// Store credentials temporarily for OTP step
let _pendingLogin = {};

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

    if (data.otp_required) {
      // Save credentials and show OTP step
      _pendingLogin = { username, password };
      document.getElementById("login-form").classList.add("hidden");
      document.getElementById("otp-form").classList.remove("hidden");
      document.getElementById("login-otp").value = "";
      document.getElementById("login-otp").focus();
      document.getElementById("otp-error").classList.add("hidden");
      return;
    }

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

async function doOtpVerify() {
  const otpCode = document.getElementById("login-otp").value.trim();
  const errEl   = document.getElementById("otp-error");

  if (otpCode.length !== 6) {
    errEl.textContent = "Entrez un code à 6 chiffres";
    errEl.classList.remove("hidden");
    return;
  }

  try {
    const resp = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: _pendingLogin.username,
        password: _pendingLogin.password,
        otp_code: otpCode,
      }),
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
    _pendingLogin = {};
    localStorage.setItem("dm_token", data.token);
    API.token = data.token;
    document.getElementById("login-modal").classList.add("hidden");
    loadInitial();
  } catch {
    errEl.textContent = "Erreur de connexion au serveur";
    errEl.classList.remove("hidden");
  }
}

function backToLogin() {
  _pendingLogin = {};
  document.getElementById("otp-form").classList.add("hidden");
  document.getElementById("login-form").classList.remove("hidden");
  document.getElementById("login-password").value = "";
}

async function doSetupAdmin() {
  const username = document.getElementById("setup-username").value.trim();
  const password = document.getElementById("setup-password").value;
  const confirm  = document.getElementById("setup-password-confirm").value;
  const errEl    = document.getElementById("setup-error");

  if (!username) { errEl.textContent = "Nom d'utilisateur requis"; errEl.classList.remove("hidden"); return; }
  if (password.length < 6) { errEl.textContent = "Mot de passe : 6 caractères minimum"; errEl.classList.remove("hidden"); return; }
  if (password !== confirm) { errEl.textContent = "Les mots de passe ne correspondent pas"; errEl.classList.remove("hidden"); return; }

  try {
    const resp = await fetch("/api/auth/setup-admin", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!resp.ok) {
      const data = await resp.json();
      errEl.textContent = data.detail || "Erreur";
      errEl.classList.remove("hidden");
      return;
    }
    const data = await resp.json();
    localStorage.setItem("dm_token", data.token);
    API.token = data.token;
    document.getElementById("login-modal").classList.add("hidden");
    showToast("Compte admin créé avec succès !", "ok");
    loadInitial();
  } catch {
    errEl.textContent = "Erreur de connexion";
    errEl.classList.remove("hidden");
  }
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !document.getElementById("login-modal").classList.contains("hidden")) {
    if (!document.getElementById("setup-form").classList.contains("hidden")) {
      doSetupAdmin();
    } else if (!document.getElementById("otp-form").classList.contains("hidden")) {
      doOtpVerify();
    } else {
      doLogin();
    }
  }
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
  const dot   = document.getElementById("aria2-status");
  const text  = document.getElementById("server-status-text");
  const badge = document.getElementById("server-badge");
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

  loadPackages();
  loadHistory();
}

// ---- Boot ----

(async () => {
  await checkAuth();
  await loadInitial();

  WS.on("downloads_update", (data, msg) => {
    renderDownloads(data);
    if (msg && msg.packages) {
      renderPackages(msg.packages);
    }
    loadHistory();
  });
  WS.init();

  checkAria2();
  setInterval(checkAria2, 15000);
})();
