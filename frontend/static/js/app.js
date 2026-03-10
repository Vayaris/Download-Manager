// ============================================================
//  Download Manager — Main Application v6
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

// ---- Auth state ----

let _appStarted = false;

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
    if (r.status === 401) {
      if (_appStarted) { _appStarted = false; showLogin(true); }
      throw new Error("Unauthorized");
    }
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async post(url, body) {
    const r = await fetch(url, { method: "POST", headers: this._headers(), body: JSON.stringify(body) });
    if (r.status === 401) {
      if (_appStarted) { _appStarted = false; showLogin(true); }
      throw new Error("Unauthorized");
    }
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async put(url, body) {
    const r = await fetch(url, { method: "PUT", headers: this._headers(), body: JSON.stringify(body) });
    if (r.status === 401) {
      if (_appStarted) { _appStarted = false; showLogin(true); }
      throw new Error("Unauthorized");
    }
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async del(url) {
    const r = await fetch(url, { method: "DELETE", headers: this._headers() });
    if (r.status === 401) {
      if (_appStarted) { _appStarted = false; showLogin(true); }
      throw new Error("Unauthorized");
    }
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

function fmtEta(remaining, speed) {
  if (!speed || speed <= 0 || !remaining || remaining <= 0) return "";
  let s = Math.round(remaining / speed);
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m${String(s % 60).padStart(2, "0")}s`;
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h >= 24 ? `${Math.floor(h / 24)}j${h % 24}h` : `${h}h${String(m).padStart(2, "0")}m`;
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
  const label = STATUS_LABELS[status] || escHtml(status);
  const safeClass = escHtml(status);
  return `<span class="badge badge-${safeClass}"><span class="b-dot"></span>${label}</span>`;
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
  const tableSection = tbody.closest(".table-wrap");
  // Only show active downloads (not completed/failed — those go to history)
  const active = downloads.filter(d => !d.package_id && d.status !== "complete" && d.status !== "failed");

  updateStats(downloads);

  if (!active || active.length === 0) {
    // Hide the table section entirely when empty
    if (tableSection) tableSection.classList.add("dl-empty");
    tbody.innerHTML = "";
    return;
  }

  if (tableSection) tableSection.classList.remove("dl-empty");
  const standalone = active;

  // Differential rendering: update existing rows in-place to avoid DOM destruction
  const existingRows = {};
  tbody.querySelectorAll("tr[data-id]").forEach(tr => { existingRows[tr.dataset.id] = tr; });

  const newIds = new Set(standalone.map(d => d.id));

  // Remove rows that no longer exist
  for (const id of Object.keys(existingRows)) {
    if (!newIds.has(id)) existingRows[id].remove();
  }

  // Update or insert rows
  let prevRow = null;
  for (const item of standalone) {
    const existing = existingRows[item.id];
    if (existing) {
      updateDownloadRow(existing, item);
      prevRow = existing;
    } else {
      const tr = createDownloadRow(item);
      if (prevRow && prevRow.nextSibling) {
        tbody.insertBefore(tr, prevRow.nextSibling);
      } else if (!prevRow) {
        tbody.prepend(tr);
      } else {
        tbody.appendChild(tr);
      }
      prevRow = tr;
    }
  }

  // Remove empty-row if present
  const emptyRow = tbody.querySelector(".empty-row");
  if (emptyRow) emptyRow.remove();
}

function createDownloadRow(item) {
  const tr = document.createElement("tr");
  tr.dataset.id = item.id;
  tr.innerHTML = buildDownloadRowInner(item);
  return tr;
}

function updateDownloadRow(tr, item) {
  const name  = fmtName(item);
  const pct   = item.progress ? item.progress.toFixed(1) : "0.0";
  const done  = parseInt(item.downloaded || 0);
  const total = parseInt(item.size || 0);

  // Update status badge
  const statusTd = tr.querySelector(".col-status");
  const newBadge = statusBadge(item.status);
  if (statusTd && statusTd.innerHTML !== newBadge) statusTd.innerHTML = newBadge;

  // Update progress bar
  const fill = tr.querySelector(".progress-fill");
  if (fill) {
    fill.style.width = pct + "%";
    fill.className = "progress-fill " + (item.status === "complete" ? "complete"
      : item.status === "error" || item.status === "failed" ? "error"
      : item.status === "downloading" ? "downloading" : "");
  }

  // Update progress meta
  const meta = tr.querySelector(".progress-meta");
  if (meta) {
    const eta = fmtEta(total - done, item.speed);
    const etaHtml = eta ? `<span class="progress-eta">${eta}</span>` : "";
    const progressMeta = item.status === "complete"
      ? `<span class="progress-pct" style="color:var(--green)">100%</span><span class="progress-done">${escHtml(fmtBytes(total))}</span>`
      : item.status === "downloading"
      ? `<span class="progress-pct">${pct}%</span><span class="progress-done">${escHtml(fmtBytes(done))} / ${escHtml(fmtBytes(total))}</span>${etaHtml}`
      : `<span class="progress-pct">${pct}%</span><span class="progress-done">${escHtml(fmtBytes(total))}</span>`;
    meta.innerHTML = progressMeta;
  }

  // Update speed + ETA
  const speedTd = tr.querySelector(".col-speed");
  if (speedTd) {
    const eta = fmtEta(total - done, item.speed);
    speedTd.innerHTML = item.speed > 0
      ? `${escHtml(fmtSpeed(item.speed))}${eta ? `<span class="speed-eta">${eta}</span>` : ""}`
      : fmtSpeed(0);
  }

  // Update size
  const sizeTd = tr.querySelector(".col-size");
  if (sizeTd) sizeTd.textContent = fmtBytes(total);

  // Update name (only if changed)
  const nameSpan = tr.querySelector(".file-name");
  if (nameSpan && nameSpan.textContent !== name) {
    nameSpan.textContent = name;
    nameSpan.title = name;
  }

  // Update actions (pause/resume buttons change with status)
  const actionsDiv = tr.querySelector(".row-actions");
  if (actionsDiv) {
    let pauseResumeBtn = "";
    if (item.status === "downloading") {
      pauseResumeBtn = `<button class="btn-act act-pause" onclick="pauseDownload('${item.id}')" title="Mettre en pause">${ICONS.pause}</button>`;
    } else if (item.status === "paused" || item.status === "error" || item.status === "failed") {
      pauseResumeBtn = `<button class="btn-act act-resume" onclick="resumeDownload('${item.id}')" title="Reprendre">${ICONS.play}</button>`;
    }
    const newActions = `${pauseResumeBtn}<button class="btn-act act-delete" onclick="removeDownload('${item.id}')" title="Supprimer">${ICONS.trash}</button>`;
    if (actionsDiv.innerHTML !== newActions) actionsDiv.innerHTML = newActions;
  }
}

function buildDownloadRowInner(item) {
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

  let retryInfo = "";
  if (item.retry_count > 0 && item.status !== "complete") {
    retryInfo = `<span class="retry-badge" title="${escHtml(item.error_msg || '')}">${ICONS.retry} ${item.retry_count}/${item.max_retries || 5}</span>`;
  }

  const eta = fmtEta(total - done, item.speed);
  const etaHtml = eta ? `<span class="progress-eta">${eta}</span>` : "";
  const progressMeta = item.status === "complete"
    ? `<span class="progress-pct" style="color:var(--green)">100%</span><span class="progress-done">${escHtml(fmtBytes(total))}</span>`
    : item.status === "downloading"
    ? `<span class="progress-pct">${pct}%</span><span class="progress-done">${escHtml(fmtBytes(done))} / ${escHtml(fmtBytes(total))}</span>${etaHtml}`
    : `<span class="progress-pct">${pct}%</span><span class="progress-done">${escHtml(fmtBytes(total))}</span>`;

  const speedContent = item.speed > 0
    ? `${escHtml(fmtSpeed(item.speed))}${eta ? `<span class="speed-eta">${eta}</span>` : ""}`
    : escHtml(fmtSpeed(0));

  return `
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
      <td class="col-speed mono-cell">${speedContent}</td>
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
      </td>`;
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
          <tbody>${pkg.downloads.map(d => `<tr data-id="${d.id}">${buildDownloadRowInner(d)}</tr>`).join("")}</tbody>
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
  FileBrowser.elevate();
  const startPath = document.getElementById("pkg-dest-path").value.trim() || undefined;
  FileBrowser.open((path) => {
    document.getElementById("pkg-dest-path").value = path;
    document.getElementById("pkg-dest-label").textContent = path;
    document.getElementById("pkg-dest-selector").classList.add("selected");
    _pkgFileBrowserMode = false;
  }, startPath);
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

  // Count only active (non-completed, non-failed) standalone downloads
  const queue   = downloads.filter(d => !d.package_id && d.status !== "complete" && d.status !== "failed");
  const active  = queue.filter(d => d.status === "downloading").length;
  const pending = queue.filter(d => d.status === "pending" || d.status === "paused" || d.status === "error").length;

  if (queue.length === 0) { el.innerHTML = ""; return; }

  el.innerHTML = `
    <div class="stat-chip total"><span class="dot"></span>${queue.length} fichier${queue.length > 1 ? "s" : ""}</div>
    ${active > 0 ? `<div class="stat-chip active"><span class="dot"></span>${active} actif${active > 1 ? "s" : ""}</div>` : ""}
    ${pending > 0 ? `<div class="stat-chip"><span class="dot"></span>${pending} en attente</div>` : ""}
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
        <td class="col-date mono-cell">${fmtDate(item.completed_at)}</td>
        <td class="col-actions">
          <div class="row-actions">
            <button class="btn-act act-delete" onclick="deleteHistoryItem('${item.id}', false)" title="Supprimer de l'historique">${ICONS.trash}</button>
            ${item.status === 'complete' ? `<button class="btn-act act-delete" onclick="deleteHistoryItem('${item.id}', true)" title="Supprimer le fichier du disque" style="color:var(--red)">${ICONS.trash}</button>` : ''}
          </div>
        </td>
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

async function deleteHistoryItem(id, deleteFile) {
  const msg = deleteFile
    ? "Supprimer cette entrée ET le fichier du disque ?"
    : "Supprimer cette entrée de l'historique ?";
  if (!confirm(msg)) return;
  try {
    await API.del(`/api/downloads/history/${id}?delete_file=${deleteFile}`);
    showToast(deleteFile ? "Entrée et fichier supprimés" : "Entrée supprimée", "ok");
    loadHistory();
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
  }
  catch (e) { showToast("Erreur : " + e.message, "error"); }
}

async function removeAllDownloads() {
  if (!confirm("Supprimer tous les téléchargements en cours ?")) return;
  try {
    await API.post("/api/downloads/actions", { action: "remove_all" });
    showToast("Tous les téléchargements supprimés", "ok");
  } catch (e) { showToast("Erreur : " + e.message, "error"); }
}

// ============================================================
//  Auth — Single-form login (username + password + OTP inline)
//  No form switching, no race conditions.
// ============================================================

async function checkAuth() {
  try {
    const resp = await fetch("/api/auth/status");
    const status = await resp.json();

    if (!status.admin_exists) {
      showSetupForm();
      return;
    }

    const token = localStorage.getItem("dm_token");
    if (!token) {
      showLogin();
      return;
    }

    // Validate token with raw fetch (no API.get side effects)
    API.token = token;
    const check = await fetch("/api/settings/", {
      headers: { "Authorization": `Bearer ${token}` },
    });
    if (check.status === 401) {
      localStorage.removeItem("dm_token");
      API.token = "";
      showLogin();
      return;
    }

    startApp();
  } catch {
    startApp();
  }
}

function showLogin(forceReset) {
  document.getElementById("login-modal").classList.remove("hidden");
  document.getElementById("login-form").classList.remove("hidden");
  document.getElementById("setup-form").classList.add("hidden");
  // Don't reset OTP state if we're in the middle of OTP entry
  if (!_loginOtpRequired || forceReset) {
    document.getElementById("otp-group").classList.add("hidden");
    document.getElementById("login-otp").value = "";
    document.getElementById("login-username").disabled = false;
    document.getElementById("login-password").disabled = false;
    _loginOtpRequired = false;
  }
  document.getElementById("login-error").classList.add("hidden");
}

function resetLoginForm() {
  _loginOtpRequired = false;
  _loginBusy = false;
  showLogin(true);
  const sub = document.querySelector("#login-form .login-sub");
  if (sub) sub.textContent = "Connectez-vous pour accéder à l'interface";
  document.getElementById("login-username").value = "";
  document.getElementById("login-password").value = "";
  document.getElementById("login-username").focus();
}

function showSetupForm() {
  document.getElementById("login-modal").classList.remove("hidden");
  document.getElementById("login-form").classList.add("hidden");
  document.getElementById("setup-form").classList.remove("hidden");
}

// doLogin handles both initial login and OTP submission in one function.
// First call: sends username+password. If OTP required, reveals the OTP field.
// Second call: sends username+password+otp_code.
let _loginOtpRequired = false;
let _loginBusy = false;

async function doLogin() {
  if (_loginBusy) return;

  const username = document.getElementById("login-username").value;
  const password = document.getElementById("login-password").value;
  const otpCode  = document.getElementById("login-otp").value.trim();
  const errEl    = document.getElementById("login-error");

  // If in OTP phase but no code entered yet, just focus OTP field
  if (_loginOtpRequired && !otpCode) {
    document.getElementById("login-otp").focus();
    return;
  }

  errEl.classList.add("hidden");
  _loginBusy = true;

  // Build request body
  const body = { username, password };
  if (_loginOtpRequired && otpCode) {
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
      if (_loginOtpRequired) {
        document.getElementById("login-otp").value = "";
        document.getElementById("login-otp").focus();
      }
      _loginBusy = false;
      return;
    }

    const data = await resp.json();

    if (data.otp_required && !_loginOtpRequired) {
      // Show OTP field inline, lock username/password fields
      _loginOtpRequired = true;
      document.getElementById("login-username").disabled = true;
      document.getElementById("login-password").disabled = true;
      document.getElementById("otp-group").classList.remove("hidden");
      document.getElementById("login-otp").value = "";
      document.getElementById("login-otp").focus();
      // Update subtitle to indicate OTP step
      const sub = document.querySelector("#login-form .login-sub");
      if (sub) sub.innerHTML = 'Vérification en deux étapes requise <a href="#" onclick="resetLoginForm();return false" style="display:block;margin-top:6px;font-size:12px">Changer de compte</a>';
      _loginBusy = false;
      return;
    }

    // Success
    _loginOtpRequired = false;
    _loginBusy = false;
    loginSuccess(data.token);
  } catch {
    errEl.textContent = "Erreur de connexion au serveur";
    errEl.classList.remove("hidden");
    _loginBusy = false;
  }
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
    showToast("Compte admin créé avec succès !", "ok");
    loginSuccess(data.token);
  } catch {
    errEl.textContent = "Erreur de connexion";
    errEl.classList.remove("hidden");
  }
}

function loginSuccess(token) {
  localStorage.setItem("dm_token", token);
  API.token = token;
  document.getElementById("login-modal").classList.add("hidden");
  // Reset form state
  document.getElementById("login-username").disabled = false;
  document.getElementById("login-password").disabled = false;
  _loginOtpRequired = false;
  _loginBusy = false;
  const sub = document.querySelector("#login-form .login-sub");
  if (sub) sub.textContent = "Connectez-vous pour accéder à l'interface";
  startApp();
}

// Enter key handler
document.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !document.getElementById("login-modal").classList.contains("hidden")) {
    if (!document.getElementById("setup-form").classList.contains("hidden")) {
      doSetupAdmin();
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
  } catch {}

  loadPackages();
  loadHistory();
}

// ---- Start app (called ONLY after auth is confirmed) ----

function startApp() {
  if (_appStarted) return;
  _appStarted = true;

  loadInitial();

  WS.on("downloads_update", (data, msg) => {
    renderDownloads(data);
    if (msg && msg.packages) {
      renderPackages(msg.packages);
    }
    loadHistory();
  });
  WS.init();

  if (typeof initAccountButton === "function") initAccountButton();
}

// ---- Boot ----

checkAuth();
