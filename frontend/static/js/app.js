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

// ---- API helper (delegates to shared apiFetch from api.js) ----

const API = apiFetch;
API._handleUnauth = function() {
  if (_appStarted) { _appStarted = false; showLogin(true); }
};

// ---- Formatters (aliases to shared api.js) ----

const fmtBytes = formatSize;
const fmtSpeed = formatSpeed;

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
  // Append "Z" only if the string has no timezone info already
  const hasTz = /[Zz]$/.test(iso) || /[+-]\d{2}:\d{2}$/.test(iso);
  const d = new Date(hasTz ? iso : iso + "Z");
  if (isNaN(d.getTime())) return "\u2014";
  const loc = t("date_locale");
  return d.toLocaleDateString(loc, { day: "2-digit", month: "2-digit", year: "2-digit" })
    + " " + d.toLocaleTimeString(loc, { hour: "2-digit", minute: "2-digit" });
}

function escJs(value) {
  return escHtml(String(value || "")
    .replace(/\\/g, "\\\\")
    .replace(/'/g, "\\'")
    .replace(/\r/g, "\\r")
    .replace(/\n/g, "\\n"));
}

// escHtml is provided by api.js

// ---- Status badge ----

const STATUS_LABELS = {
  pending:     function() { return t("status_pending"); },
  submitting:  function() { return t("status_submitting"); },
  downloading: function() { return t("status_downloading"); },
  paused:      function() { return t("status_paused"); },
  complete:    function() { return t("status_complete"); },
  error:       function() { return t("status_error"); },
  failed:      function() { return t("status_failed"); },
  debrid:      function() { return t("status_debrid"); },
};

function statusBadge(status) {
  const labelFn = STATUS_LABELS[status];
  const label = labelFn ? labelFn() : escHtml(status);
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
    showToast(t("copy_ok"), "ok");
  } catch {
    showToast(t("copy_fail"), "error");
  }
}

// ---- Paste from clipboard ----

async function pasteFromClipboard() {
  try {
    const text = await navigator.clipboard.readText();
    const textarea = document.getElementById("links-input");
    addUnifiedLinkText([textarea.value, text].filter(value => value.trim()).join("\n"));
    textarea.value = "";
    updateUnifiedSourceState();
    textarea.focus();
    showToast(text.trim() ? t("paste_ok") : t("paste_empty"), text.trim() ? "ok" : "error");
  } catch {
    showToast(t("paste_fail"), "error");
  }
}

// ---- Unified links / magnets / torrents submission ----

let unifiedLinkSources = [];
let unifiedTorrentFiles = [];
let unifiedSourcesExpanded = false;

function unifiedLinks() {
  const draft = document.getElementById("links-input").value
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(Boolean);
  return [...unifiedLinkSources, ...draft];
}

function unifiedLinkCount() {
  return unifiedLinks().length;
}

function unifiedSourceType(value) {
  return value.toLowerCase().startsWith("magnet:") ? "magnet" : "link";
}

function addUnifiedLinkText(text) {
  const links = String(text || "").split(/\r?\n/).map(line => line.trim()).filter(Boolean);
  unifiedLinkSources.push(...links);
  renderUnifiedSources();
}

function unifiedSourceMeta(source) {
  if (source.kind === "torrent") return fmtBytes(source.file.size);
  if (source.kind === "magnet") return "";
  try { return new URL(source.value).hostname; }
  catch { return ""; }
}

function updateUnifiedSourceState() {
  const count = unifiedLinkCount() + unifiedTorrentFiles.length;
  document.getElementById("unified-package-name-wrap").classList.toggle("hidden", count < 2);
  const label = document.getElementById("unified-submit-label");
  label.textContent = count ? t("unified_add_count", { n: count }) : t("btn_add");
}

function renderUnifiedSources() {
  const links = unifiedLinkSources.map((value, index) => ({ kind: unifiedSourceType(value), value, index }));
  const files = unifiedTorrentFiles.map((file, index) => ({ kind: "torrent", file, index }));
  const sources = [...links, ...files];
  const container = document.getElementById("unified-sources");
  container.classList.toggle("hidden", sources.length === 0);
  const visible = unifiedSourcesExpanded ? sources : sources.slice(0, 6);
  container.innerHTML = visible.map(source => {
    const isFile = source.kind === "torrent";
    const value = isFile ? source.file.name : source.value;
    const meta = unifiedSourceMeta(source);
    const remove = isFile ? `removeUnifiedTorrentFile(${source.index})` : `removeUnifiedLink(${source.index})`;
    return `<div class="unified-source-row">
      <span class="unified-source-type ${source.kind}">${isFile ? ICONS.pkg : ICONS.copy}<small>${t(`composer_type_${source.kind}`)}</small></span>
      <span class="unified-source-name" title="${escHtml(value)}">${escHtml(value)}</span>
      <span class="unified-source-meta">${escHtml(meta)}</span>
      <button type="button" onclick="${remove}" aria-label="${t("composer_remove_source")}">×</button>
    </div>`;
  }).join("") + (sources.length > 6 ? `
    <button type="button" class="unified-sources-toggle" onclick="toggleUnifiedSources()">
      ${unifiedSourcesExpanded ? t("composer_show_less") : t("composer_show_more", { n: sources.length - 6 })}
    </button>` : "");
  updateUnifiedSourceState();
}

function toggleUnifiedSources() {
  unifiedSourcesExpanded = !unifiedSourcesExpanded;
  renderUnifiedSources();
}

function removeUnifiedLink(index) {
  unifiedLinkSources.splice(index, 1);
  renderUnifiedSources();
}

function addUnifiedTorrentFiles(files) {
  let ignored = 0;
  for (const file of Array.from(files || [])) {
    if (!file.name.toLowerCase().endsWith(".torrent")) { ignored++; continue; }
    const duplicate = unifiedTorrentFiles.some(item => item.name === file.name && item.size === file.size && item.lastModified === file.lastModified);
    if (!duplicate) unifiedTorrentFiles.push(file);
  }
  document.getElementById("unified-torrent-input").value = "";
  renderUnifiedSources();
  if (ignored) showToast(t("torrent_files_ignored"), "error");
}

function removeUnifiedTorrentFile(index) {
  unifiedTorrentFiles.splice(index, 1);
  renderUnifiedSources();
}

async function addUnifiedSources() {
  const textarea = document.getElementById("links-input");
  const links = unifiedLinks().join("\n");
  const sourceCount = unifiedLinks().length + unifiedTorrentFiles.length;
  if (!sourceCount) { showToast(t("unified_empty"), "error"); return; }

  let destination = getDestinationValue("dest-path");
  if (!destination) {
    try {
      const cfg = await API.get("/api/settings/");
      destination = cfg.default_destination || "/opt/download-manager/downloads";
    } catch {
      destination = "/opt/download-manager/downloads";
    }
  }

  const form = new FormData();
  form.append("links", links);
  form.append("destination", destination);
  const customName = document.getElementById("unified-package-name").value.trim();
  form.append("package_name", customName || t("auto_batch_name", { date: new Date().toLocaleString(getLang()) }));
  unifiedTorrentFiles.forEach(file => form.append("files", file));

  const button = document.getElementById("unified-submit");
  button.disabled = true;
  button.classList.add("loading");
  try {
    const result = await preflightAndCommit(form);
    textarea.value = "";
    unifiedLinkSources = [];
    unifiedTorrentFiles = [];
    unifiedSourcesExpanded = false;
    document.getElementById("unified-package-name").value = "";
    renderUnifiedSources();
    const message = result.package_name
      ? t("batch_added", { n: result.added, name: result.package_name })
      : t("unified_added", { n: result.added });
    showToast(result.failed ? `${message} · ${t("batch_failed", { n: result.failed })}` : message, result.failed ? "error" : "ok");
  } catch (error) {
    showToast(t("error_prefix") + error.message, "error");
  } finally {
    button.disabled = false;
    button.classList.remove("loading");
    updateUnifiedSourceState();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const card = document.getElementById("unified-add-card");
  const overlay = document.getElementById("torrent-drop-overlay");
  const textarea = document.getElementById("links-input");
  let dragDepth = 0;
  const hasDraggedFiles = event => Array.from(event.dataTransfer?.types || []).includes("Files");
  textarea.addEventListener("input", updateUnifiedSourceState);
  textarea.addEventListener("paste", event => {
    const text = event.clipboardData?.getData("text") || "";
    if (!text.trim()) return;
    event.preventDefault();
    addUnifiedLinkText(text);
  });
  textarea.addEventListener("keydown", event => {
    if (event.key !== "Enter" || event.shiftKey || event.ctrlKey || event.metaKey) return;
    event.preventDefault();
    addUnifiedLinkText(textarea.value);
    textarea.value = "";
    updateUnifiedSourceState();
  });
  document.getElementById("dest-path-text")?.addEventListener("input", renderQuickDestinations);
  card.addEventListener("dragenter", event => {
    if (!hasDraggedFiles(event)) return;
    event.preventDefault();
    dragDepth++;
    overlay.classList.remove("hidden");
  });
  card.addEventListener("dragover", event => {
    if (hasDraggedFiles(event)) event.preventDefault();
  });
  card.addEventListener("dragleave", event => {
    event.preventDefault();
    dragDepth = Math.max(0, dragDepth - 1);
    if (!dragDepth) overlay.classList.add("hidden");
  });
  card.addEventListener("drop", event => {
    event.preventDefault();
    dragDepth = 0;
    overlay.classList.add("hidden");
    addUnifiedTorrentFiles(event.dataTransfer.files);
  });
  renderUnifiedSources();
});

// ---- Downloads workspace ----

const downloadWorkspace = {
  downloads: [],
  packages: [],
  torrents: [],
  preferences: { favorites: [], recents: [] },
  storage: [],
  recentGroups: [],
};

function activeWorkspaceDownloads() {
  return downloadWorkspace.downloads.filter(item => item.status !== "complete" && item.status !== "failed");
}

function activeWorkspaceTorrents() {
  const packageIds = new Set(activeWorkspaceDownloads().map(item => item.package_id).filter(Boolean));
  return downloadWorkspace.torrents.filter(item => !item.package_id || !packageIds.has(item.package_id));
}

function updateDownloadWorkspace() {
  const downloads = activeWorkspaceDownloads();
  const torrents = activeWorkspaceTorrents();
  const count = downloads.length + torrents.length;
  document.getElementById("download-controls")?.classList.toggle("hidden", downloads.length === 0);
  document.getElementById("download-dashboard")?.classList.toggle("hidden", count > 0);
  document.getElementById("active-tab-count").textContent = count;
  updateStats(downloads, torrents);
}

function matchingStorage(path) {
  return downloadWorkspace.storage
    .filter(item => path === item.path || path.startsWith(`${String(item.path).replace(/\/$/, "")}/`))
    .sort((a, b) => b.path.length - a.path.length)[0];
}

function quickPlaceHtml(item) {
  const storage = matchingStorage(item.path);
  const selected = getDestinationValue("dest-path") === item.path;
  const storageText = storage?.available
    ? `${item.storage_label} · ${t("quick_free", { size: fmtBytes(storage.free) })}`
    : item.storage_label;
  return `<button type="button" class="quick-place${selected ? " selected" : ""}${item.available ? "" : " unavailable"}"
      onclick="selectQuickDestination('${escJs(item.path)}')" ${item.available ? "" : "disabled"}>
    <span class="quick-place-icon">${ICONS.folder}</span>
    <span><strong>${escHtml(item.name)}</strong><small title="${escHtml(item.path)}">${escHtml(storageText)}</small></span>
  </button>`;
}

function renderQuickDestinations() {
  const favorites = downloadWorkspace.preferences.favorites || [];
  const favoritePaths = new Set(favorites.map(item => item.path));
  const recents = (downloadWorkspace.preferences.recents || []).filter(item => !favoritePaths.has(item.path));
  document.getElementById("quick-favorites-wrap").classList.toggle("hidden", favorites.length === 0);
  document.getElementById("quick-recents-wrap").classList.toggle("hidden", recents.length === 0);
  document.getElementById("quick-destinations-empty").classList.toggle("hidden", favorites.length + recents.length > 0);
  document.getElementById("quick-favorites").innerHTML = favorites.slice(0, 6).map(quickPlaceHtml).join("");
  document.getElementById("quick-recents").innerHTML = recents.slice(0, 4).map(quickPlaceHtml).join("");
}

async function selectQuickDestination(path) {
  setDestinationValue("dest-path", path);
  renderQuickDestinations();
  try {
    await API.post("/api/files/recents", { path });
  } catch {}
}

function renderRecentActivity() {
  const container = document.getElementById("recent-activity");
  if (!container) return;
  const groups = downloadWorkspace.recentGroups;
  document.getElementById("recent-activity-empty").classList.toggle("hidden", groups.length > 0);
  container.innerHTML = groups.map(group => {
    const meta = group.kind === "package"
      ? t("history_files_count", { n: group.item_count })
      : fmtBytes(group.size);
    return `<button type="button" class="recent-activity-item" onclick="openHistoryDetails('${group.id}')">
      <span class="recent-activity-status ${group.status}">${group.status === "complete" ? ICONS.check : "!"}</span>
      <span class="recent-activity-copy"><strong title="${escHtml(group.name)}">${escHtml(group.name)}</strong><small>${escHtml(meta)} · ${fmtDate(group.completed_at)}</small></span>
      <span class="recent-activity-chevron">${ICONS.chevRight}</span>
    </button>`;
  }).join("");
}

async function loadDownloadDashboard() {
  try {
    const [preferences, storage] = await Promise.all([
      API.get("/api/files/preferences"),
      API.get("/api/settings/storage"),
    ]);
    downloadWorkspace.preferences = preferences;
    downloadWorkspace.storage = storage;
    renderQuickDestinations();
  } catch {}
}

let lastRuntimeStatus = null;

function renderRuntimeAlert(status = lastRuntimeStatus) {
  if (status) lastRuntimeStatus = status;
  const alert = document.getElementById("runtime-alert");
  if (!alert) return;
  const websocketOk = WS.isConnected();
  const warnings = [];
  if (!websocketOk) warnings.push(t("runtime_ws_unavailable"));
  if (status && !status.queue_running) warnings.push(t("runtime_queue_unavailable"));
  if (status && !status.aria2_ok) warnings.push(t("runtime_aria2_unavailable"));
  if (status?.queue_error) warnings.push(status.queue_error);
  alert.classList.toggle("hidden", warnings.length === 0);
  alert.innerHTML = warnings.length ? `<strong>${t("runtime_alert_title")}</strong><span>${escHtml(warnings.join(" · "))}</span>` : "";
}

async function checkRuntimeStatus() {
  try {
    renderRuntimeAlert(await API.get("/api/settings/runtime-status"));
  } catch {
    renderRuntimeAlert();
  }
}

// ---- Render downloads ----

function renderDownloads(downloads) {
  downloadWorkspace.downloads = downloads || [];
  const tbody = document.getElementById("dl-tbody");
  const tableSection = tbody.closest(".table-wrap");
  // Only show active downloads (not completed/failed — those go to history)
  const active = downloads.filter(d => !d.package_id && d.status !== "complete" && d.status !== "failed");

  updateDownloadWorkspace();

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
      pauseResumeBtn = `<button class="btn-act act-pause" onclick="pauseDownload('${item.id}')" title="${t("btn_pause")}">${ICONS.pause}</button>`;
    } else if (item.status === "paused" || item.status === "error" || item.status === "failed") {
      pauseResumeBtn = `<button class="btn-act act-resume" onclick="resumeDownload('${item.id}')" title="${t("btn_resume")}">${ICONS.play}</button>`;
    }
    const newActions = `${pauseResumeBtn}<button class="btn-act act-delete" onclick="removeDownload('${item.id}')" title="${t("btn_delete")}">${ICONS.trash}</button>`;
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
    pauseResumeBtn = `<button class="btn-act act-pause" onclick="pauseDownload('${item.id}')" title="${t("btn_pause")}">${ICONS.pause}</button>`;
  } else if (item.status === "paused" || item.status === "error" || item.status === "failed") {
    pauseResumeBtn = `<button class="btn-act act-resume" onclick="resumeDownload('${item.id}')" title="${t("btn_resume")}">${ICONS.play}</button>`;
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
          <button class="btn-act act-delete" onclick="removeDownload('${item.id}')" title="${t("btn_delete")}">${ICONS.trash}</button>
        </div>
      </td>`;
}

// ---- Packages rendering ----

let expandedPackages = new Set();

function renderPackages(packages) {
  downloadWorkspace.packages = packages || [];
  const section = document.getElementById("packages-section");
  const list = document.getElementById("packages-list");

  if (!packages || packages.length === 0) {
    section.classList.add("hidden");
    updateDownloadWorkspace();
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

    const pkgStatusLabel = pkg.status === "complete" ? t("pkg_status_complete")
      : pkg.status === "partial" ? t("pkg_status_partial")
      : t("pkg_status_active");

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
            <span class="pkg-meta">${pkg.completed_files || 0}/${pkg.total_files || 0} ${t("pkg_files")} \u2022 ${escHtml(fmtBytes(pkg.total_size))}</span>
          </div>
          <div class="pkg-progress-wrap">
            <div class="progress-track" style="width:120px">
              <div class="progress-fill ${statusClass}" style="width:${pct}%"></div>
            </div>
            <span class="progress-pct">${pct}%</span>
          </div>
          <span class="badge badge-${statusClass}" style="margin-left:8px"><span class="b-dot"></span>${pkgStatusLabel}</span>
          ${totalSpeed > 0 ? `<span class="pkg-speed mono-cell">${escHtml(fmtSpeed(totalSpeed))}</span>` : ''}
          <button class="btn-act act-delete" onclick="event.stopPropagation();removePackage('${pkg.id}')" title="${t("btn_delete_pkg")}">${ICONS.trash}</button>
        </div>
        ${downloadsHtml}
      </div>`;
  }).join("");
  updateDownloadWorkspace();
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
    showToast(t("pkg_deleted"), "ok");
  } catch (e) { showToast(t("error_prefix") + e.message, "error"); }
}

// ---- Stats chips ----

function updateStats(downloads, torrents = []) {
  const el = document.getElementById("stats-chips");
  if (!el) return;

  const queue = [...downloads, ...torrents];
  const active = queue.filter(item => item.status === "downloading" || item.status === "processing" || item.status === "ready_importing").length;
  const pending = Math.max(0, queue.length - active);
  const totalSpeed = queue.reduce((sum, item) => sum + Number(item.speed || 0), 0);

  if (queue.length === 0) { el.innerHTML = ""; return; }

  el.innerHTML = `
    <div class="stat-chip total"><span class="dot"></span>${t("stats_files", { n: queue.length, s: queue.length > 1 ? "s" : "" })}</div>
    ${active > 0 ? `<div class="stat-chip active"><span class="dot"></span>${t("stats_active", { n: active, s: active > 1 ? "s" : "" })}</div>` : ""}
    ${pending > 0 ? `<div class="stat-chip"><span class="dot"></span>${t("stats_pending", { n: pending })}</div>` : ""}
    ${totalSpeed > 0 ? `<div class="stat-chip speed"><span class="dot"></span>${escHtml(fmtSpeed(totalSpeed))}</div>` : ""}
  `;
}

// ---- History ----

const historyState = {
  scope: "all", cursor: null, groups: [], details: new Map(),
  selecting: false, selected: new Set(), loading: false,
};

function switchDownloadView(view) {
  const history = view === "history";
  document.getElementById("active-view").classList.toggle("hidden", history);
  document.getElementById("history-section").classList.toggle("hidden", !history);
  document.getElementById("active-tab").classList.toggle("active", !history);
  document.getElementById("history-tab").classList.toggle("active", history);
  document.getElementById("active-tab").setAttribute("aria-selected", String(!history));
  document.getElementById("history-tab").setAttribute("aria-selected", String(history));
  closeHistoryMenus();
  if (history) loadHistory(true);
}

function historyInteractionInProgress() {
  return historyState.selecting
    || !document.getElementById("history-detail-panel").classList.contains("hidden")
    || Boolean(document.querySelector(".history-card.expanded"));
}

function historyDayLabel(value) {
  const date = new Date(value);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  const key = date.toDateString();
  if (key === today.toDateString()) return t("history_today");
  if (key === yesterday.toDateString()) return t("history_yesterday");
  return date.toLocaleDateString(t("date_locale"), { weekday: "long", day: "numeric", month: "long", year: "numeric" });
}

function historyStatus(group) {
  if (group.status === "partial") {
    return `<span class="badge badge-error"><span class="b-dot"></span>${t("history_partial")}</span>`;
  }
  return statusBadge(group.status);
}

function renderHistorySummary(summary) {
  document.getElementById("history-summary").innerHTML = `
    <div><strong>${summary.completed_today}</strong><span>${t("history_completed_today")}</span></div>
    <div><strong>${fmtBytes(summary.total_bytes)}</strong><span>${t("history_total_volume")}</span></div>
    <div class="${summary.failed ? "has-error" : ""}"><strong>${summary.failed}</strong><span>${t("history_failures")}</span></div>`;
  document.getElementById("history-failed-count").textContent = summary.failed;
  document.getElementById("history-tab-count").textContent = summary.total;
}

function renderHistoryGroups() {
  const container = document.getElementById("history-groups");
  const empty = document.getElementById("history-empty");
  empty.classList.toggle("hidden", historyState.groups.length > 0);
  let lastDay = "";
  container.innerHTML = historyState.groups.map(group => {
    const day = historyDayLabel(group.completed_at);
    const heading = day !== lastDay ? `<div class="history-day">${escHtml(day)}</div>` : "";
    lastDay = day;
    const packageMeta = group.kind === "package"
      ? `${t("history_files_count", { n: group.item_count })} · ${group.complete_count} ${t("history_success_short")} · ${group.failed_count} ${t("history_failed_short")}`
      : fmtBytes(group.size);
    return `${heading}<article class="history-card ${group.kind}" data-history-group="${group.id}">
      <label class="history-checkbox ${historyState.selecting ? "" : "hidden"}" onclick="event.stopPropagation()">
        <input type="checkbox" ${historyState.selected.has(group.id) ? "checked" : ""} onchange="selectHistoryGroup('${group.id}',this.checked)">
      </label>
      <button class="history-card-main" onclick="${group.kind === "package" ? `toggleHistoryGroup('${group.id}')` : `openHistoryDetails('${group.id}')`}">
        <span class="history-chevron">${group.kind === "package" ? ICONS.chevRight : ICONS.check}</span>
        <span class="history-card-copy"><strong title="${escHtml(group.name)}">${escHtml(group.name)}</strong><small>${escHtml(packageMeta)}</small></span>
      </button>
      <div class="history-card-status">${historyStatus(group)}</div>
      <div class="history-card-meta"><span>${fmtBytes(group.size)}</span><span>${fmtDate(group.completed_at)}</span></div>
      <button class="history-card-menu" onclick="openHistoryActions(event,'${group.id}')" aria-label="${t("col_actions")}">•••</button>
      <div class="history-card-destination" title="${escHtml(group.destination)}">${ICONS.folder}<span>${escHtml(group.destination || t("history_multiple_destinations"))}</span></div>
      <div id="history-children-${group.id}" class="history-children hidden"></div>
    </article>`;
  }).join("");
  renderRecentActivity();
}

async function loadHistory(reset = true) {
  if (historyState.loading) return;
  historyState.loading = true;
  try {
    if (reset) {
      historyState.cursor = null;
      historyState.groups = [];
      historyState.details.clear();
    }
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const cursor = historyState.cursor ? `&cursor=${encodeURIComponent(historyState.cursor)}` : "";
    const data = await API.get(`/api/downloads/history/view?scope=${historyState.scope}&limit=30&today_from=${encodeURIComponent(today.toISOString())}${cursor}`);
    historyState.groups.push(...data.groups);
    if (reset && historyState.scope === "all") downloadWorkspace.recentGroups = data.groups.slice(0, 3);
    historyState.cursor = data.next_cursor;
    renderHistorySummary(data.summary);
    renderHistoryGroups();
    document.getElementById("history-load-more").classList.toggle("hidden", !data.next_cursor);
  } catch (error) {
    showToast(t("error_prefix") + error.message, "error");
  } finally {
    historyState.loading = false;
  }
}

function loadMoreHistory() { loadHistory(false); }

function setHistoryScope(scope) {
  historyState.scope = scope;
  document.querySelectorAll("[data-history-scope]").forEach(button => button.classList.toggle("active", button.dataset.historyScope === scope));
  toggleHistorySelection(false);
  loadHistory(true);
}

async function getHistoryGroup(groupId) {
  if (!historyState.details.has(groupId)) {
    historyState.details.set(groupId, await API.get(`/api/downloads/history/groups/${encodeURIComponent(groupId)}`));
  }
  return historyState.details.get(groupId);
}

function historyChildRow(item, groupId) {
  return `<div class="history-child">
    <span class="history-child-status">${statusBadge(item.status)}</span>
    <button class="history-child-name" onclick="openHistoryDetails('${groupId}','${item.id}')">${escHtml(item.name || item.url)}</button>
    <span class="history-child-size">${fmtBytes(item.size)}</span>
    <button class="history-card-menu" onclick="openHistoryActions(event,'${groupId}','${item.id}')">•••</button>
  </div>`;
}

async function toggleHistoryGroup(groupId) {
  const child = document.getElementById(`history-children-${groupId}`);
  const card = child.closest(".history-card");
  if (!child.classList.contains("hidden")) {
    child.classList.add("hidden");
    card.classList.remove("expanded");
    return;
  }
  child.innerHTML = `<div class="history-child-loading">${t("history_loading")}</div>`;
  child.classList.remove("hidden");
  card.classList.add("expanded");
  try {
    const detail = await getHistoryGroup(groupId);
    child.innerHTML = detail.items.map(item => historyChildRow(item, groupId)).join("");
  } catch (error) {
    child.innerHTML = `<div class="history-child-loading">${escHtml(error.message)}</div>`;
  }
}

function historyDetailHtml(item) {
  const error = item.error_msg ? `<div class="history-detail-error"><span>${t("history_error_detail")}</span><p>${escHtml(item.error_msg)}</p></div>` : "";
  return `<div class="history-detail-title">${statusBadge(item.status)}<h4>${escHtml(item.name || item.url)}</h4></div>
    <dl class="history-detail-list">
      <dt>${t("col_size")}</dt><dd>${fmtBytes(item.size)}</dd>
      <dt>${t("col_dest")}</dt><dd class="mono-cell">${escHtml(item.destination || "—")}</dd>
      <dt>${t("history_source")}</dt><dd class="mono-cell">${escHtml(item.url || "—")}</dd>
      <dt>${t("history_started")}</dt><dd>${fmtDate(item.created_at)}</dd>
      <dt>${t("history_finished")}</dt><dd>${fmtDate(item.completed_at)}</dd>
    </dl>${error}
    <div class="history-detail-actions">
      <button class="btn" onclick="copyToClipboard('${escJs(item.destination || "")}')">${t("history_copy_path")}</button>
      ${item.retryable ? `<button class="btn" onclick="retryHistoryItem('${item.id}')">${t("history_retry")}</button>` : ""}
      <button class="btn" onclick="removeHistoryIds(['${item.id}'])">${t("btn_delete_history")}</button>
      ${item.status === "complete" ? `<button class="btn btn-danger" onclick="deleteHistoryItem('${item.id}',true)">${t("btn_delete_file")}</button>` : ""}
    </div>`;
}

async function openHistoryDetails(groupId, itemId = "") {
  closeHistoryMenus();
  try {
    const detail = await getHistoryGroup(groupId);
    const item = detail.items.find(entry => entry.id === itemId) || detail.items[0];
    document.getElementById("history-detail-content").innerHTML = historyDetailHtml(item);
    document.getElementById("history-detail-panel").classList.remove("hidden");
    document.getElementById("history-detail-panel").setAttribute("aria-hidden", "false");
    document.getElementById("history-detail-backdrop").classList.remove("hidden");
  } catch (error) {
    showToast(t("error_prefix") + error.message, "error");
  }
}

function closeHistoryDetails() {
  document.getElementById("history-detail-panel").classList.add("hidden");
  document.getElementById("history-detail-panel").setAttribute("aria-hidden", "true");
  document.getElementById("history-detail-backdrop").classList.add("hidden");
}

function closeHistoryMenus() {
  document.getElementById("history-global-menu")?.classList.add("hidden");
  document.getElementById("history-context-menu")?.remove();
}

function toggleHistoryGlobalMenu(event) {
  event.stopPropagation();
  document.getElementById("history-global-menu").classList.toggle("hidden");
}

async function openHistoryActions(event, groupId, itemId = "") {
  event.stopPropagation();
  closeHistoryMenus();
  let detail;
  try {
    detail = await getHistoryGroup(groupId);
  } catch (error) {
    showToast(t("error_prefix") + error.message, "error");
    return;
  }
  const item = itemId ? detail.items.find(entry => entry.id === itemId) : (detail.items.length === 1 ? detail.items[0] : null);
  const ids = item ? [item.id] : detail.items.map(entry => entry.id);
  const menu = document.createElement("div");
  menu.id = "history-context-menu";
  menu.className = "history-menu history-context-menu";
  menu.innerHTML = `
    <button onclick="${item ? `openHistoryDetails('${groupId}','${item.id}')` : `toggleHistoryGroup('${groupId}');closeHistoryMenus()`}">${item ? t("history_details") : t("history_show_files")}</button>
    <button onclick="copyToClipboard('${escJs((item || detail.items[0]).destination || "")}');closeHistoryMenus()">${t("history_copy_path")}</button>
    ${item?.retryable ? `<button onclick="retryHistoryItem('${item.id}')">${t("history_retry")}</button>` : ""}
    <button onclick='removeHistoryIds(${JSON.stringify(ids)})'>${t("btn_delete_history")}</button>
    ${item?.status === "complete" ? `<button class="danger" onclick="deleteHistoryItem('${item.id}',true)">${t("btn_delete_file")}</button>` : ""}`;
  document.body.appendChild(menu);
  const rect = event.currentTarget.getBoundingClientRect();
  menu.style.left = `${Math.max(8, Math.min(rect.right - 210, window.innerWidth - 218))}px`;
  menu.style.top = `${Math.min(rect.bottom + 4, window.innerHeight - menu.offsetHeight - 8)}px`;
}

function toggleHistorySelection(force) {
  historyState.selecting = typeof force === "boolean" ? force : !historyState.selecting;
  if (!historyState.selecting) historyState.selected.clear();
  document.getElementById("history-selection-bar").classList.toggle("hidden", !historyState.selecting);
  document.getElementById("history-select-toggle").classList.toggle("active", historyState.selecting);
  renderHistoryGroups();
  updateHistorySelectionCount();
}

async function selectHistoryGroup(groupId, checked) {
  if (checked) historyState.selected.add(groupId); else historyState.selected.delete(groupId);
  updateHistorySelectionCount();
}

function updateHistorySelectionCount() {
  document.getElementById("history-selection-count").textContent = t("history_selected_count", { n: historyState.selected.size });
}

async function removeSelectedHistory() {
  const ids = [];
  for (const groupId of historyState.selected) {
    const detail = await getHistoryGroup(groupId);
    ids.push(...detail.items.map(item => item.id));
  }
  if (ids.length) await removeHistoryIds(ids);
}

async function removeHistoryIds(ids) {
  closeHistoryMenus();
  if (!confirm(t("history_confirm_remove_entries", { n: ids.length }))) return;
  try {
    await API.post("/api/downloads/history/remove", { ids });
    closeHistoryDetails();
    toggleHistorySelection(false);
    await loadHistory(true);
    showToast(t("history_deleted"), "ok");
  } catch (error) {
    showToast(t("error_prefix") + error.message, "error");
  }
}

async function clearHistory() {
  closeHistoryMenus();
  if (!confirm(t("history_confirm_clear_keep_files"))) return;
  try {
    await API.del("/api/downloads/history");
    await loadHistory(true);
    showToast(t("history_cleared"), "ok");
  } catch (e) { showToast(t("error_prefix") + e.message, "error"); }
}

async function deleteHistoryItem(id, deleteFile) {
  const msg = deleteFile ? t("history_confirm_delete_file") : t("history_confirm_delete");
  if (!confirm(msg)) return;
  try {
    await API.del(`/api/downloads/history/${id}?delete_file=${deleteFile}`);
    showToast(deleteFile ? t("history_deleted_file") : t("history_deleted"), "ok");
    closeHistoryDetails();
    closeHistoryMenus();
    loadHistory(true);
  } catch (e) { showToast(t("error_prefix") + e.message, "error"); }
}

async function retryHistoryItem(id) {
  for (const detail of historyState.details.values()) {
    const item = detail.items.find(entry => entry.id === id);
    if (!item) continue;
    const form = new FormData();
    form.append("links", item.url);
    form.append("destination", item.destination);
    form.append("package_name", "");
    try {
      const result = await preflightAndCommit(form);
      closeHistoryDetails();
      closeHistoryMenus();
      switchDownloadView("active");
      showToast(t("history_retry_started", { n: result.added }), "ok");
    } catch (error) {
      showToast(t("error_prefix") + error.message, "error");
    }
    return;
  }
}

document.addEventListener("click", event => {
  if (!event.target.closest(".history-more-wrap") && !event.target.closest(".history-context-menu")) closeHistoryMenus();
});
document.addEventListener("keydown", event => {
  if (event.key === "Escape") { closeHistoryMenus(); closeHistoryDetails(); }
});

// ---- Render torrents ----

function renderTorrents(torrents) {
  downloadWorkspace.torrents = torrents || [];
  const section = document.getElementById("torrents-section");
  const list = document.getElementById("torrents-list");

  if (!torrents || torrents.length === 0) {
    section.classList.add("hidden");
    updateDownloadWorkspace();
    return;
  }

  section.classList.remove("hidden");

  list.innerHTML = torrents.map(torr => {
    const pct = torr.progress ? torr.progress.toFixed(1) : "0.0";
    const isError = torr.status === "error" || torr.status === "import_failed";
    const statusClass = isError ? "error" : "downloading";
    const statusLabels = {
      error: t("torrent_status_error"),
      import_failed: t("torrent_status_import_failed"),
      ready_importing: t("torrent_status_importing"),
      processing: t("torrent_status_processing"),
    };
    const statusLabel = statusLabels[torr.status] || t("torrent_status_processing");
    const detail = torr.status_message ? ` \u2022 ${escHtml(torr.status_message)}` : "";

    return `
      <div class="torrent-card">
        <div class="torrent-header">
          <div class="torrent-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242"/><path d="M12 12v9"/><path d="m8 17 4 4 4-4"/></svg>
          </div>
          <div class="torrent-info">
            <span class="torrent-name" title="${escHtml(torr.name)}">${escHtml(torr.name || 'Torrent')}</span>
            <span class="torrent-meta">
              ${escHtml(fmtBytes(torr.size))}
              ${torr.speed > 0 ? ` \u2022 ${escHtml(fmtSpeed(torr.speed))}` : ''}
              ${torr.seeders > 0 ? ` \u2022 ${torr.seeders} seed${torr.seeders > 1 ? 's' : ''}` : ''}
              ${detail}
            </span>
          </div>
          <div class="torrent-progress-wrap">
            <div class="progress-track" style="width:120px">
              <div class="progress-fill ${statusClass}" style="width:${pct}%"></div>
            </div>
            <span class="progress-pct">${pct}%</span>
          </div>
          <span class="badge badge-${statusClass}" style="margin-left:8px"><span class="b-dot"></span>${statusLabel}</span>
          <button class="btn-act act-delete" onclick="removeTorrent('${torr.id}')" title="${t("btn_delete")}">${ICONS.trash}</button>
        </div>
      </div>`;
  }).join("");
  updateDownloadWorkspace();
}

async function removeTorrent(id) {
  try {
    await API.del(`/api/torrents/${id}`);
    showToast(t("torrent_deleted"), "ok");
  } catch (e) { showToast(t("error_prefix") + e.message, "error"); }
}

// ---- Actions ----

function duplicateText(fr, en) {
  return getLang() === "fr" ? fr : en;
}

async function duplicateApi(path, options = {}) {
  const headers = options.headers || {};
  if (API.token) headers.Authorization = `Bearer ${API.token}`;
  const response = await fetch(path, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
  return data;
}

function chooseDuplicateActions(preflight) {
  const conflicts = preflight.items.filter(item => item.conflicts && item.conflicts.length);
  if (!conflicts.length) return Promise.resolve([]);
  return new Promise((resolve, reject) => {
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.innerHTML = `
      <div class="modal-box duplicate-modal" style="width:min(760px,calc(100vw - 24px));max-height:88vh;overflow:auto">
        <div class="modal-header"><div class="modal-header-title"><h3>${duplicateText("Doublons détectés", "Duplicates detected")}</h3></div></div>
        <div style="padding:20px">
          <p class="form-hint" style="margin-bottom:14px">${duplicateText("Choisissez une action pour chaque élément. Aucun fichier ne sera remplacé automatiquement.", "Choose an action for each item. No file will be replaced automatically.")}</p>
          <div style="display:flex;justify-content:flex-end;gap:8px;margin-bottom:12px;align-items:center">
            <label class="form-hint" for="duplicate-apply-all">${duplicateText("Appliquer à tous", "Apply to all")}</label>
            <select id="duplicate-apply-all" class="form-input" style="width:auto">
              <option value="">—</option><option value="ignore">${duplicateText("Ignorer", "Ignore")}</option>
              <option value="download">${duplicateText("Télécharger quand même", "Download anyway")}</option>
              <option value="replace">${duplicateText("Remplacer", "Replace")}</option>
            </select>
          </div>
          <div>${conflicts.map(item => {
            const details = item.conflicts.map(conflict => conflict.path || conflict.name || conflict.destination || conflict.type).join(" · ");
            return `<div class="settings-card" style="padding:12px;margin-bottom:8px">
              <strong>${escHtml(item.display_name)}</strong>
              <div class="form-hint" style="overflow-wrap:anywhere">${escHtml(details)}</div>
              <select class="form-input duplicate-action" data-source-id="${item.id}" style="margin-top:8px">
                <option value="ignore">${duplicateText("Ignorer", "Ignore")}</option>
                <option value="download">${duplicateText("Télécharger quand même", "Download anyway")}</option>
                <option value="replace">${duplicateText("Remplacer", "Replace")}</option>
              </select>
            </div>`;
          }).join("")}</div>
        </div>
        <div class="modal-footer" style="display:flex;justify-content:flex-end;gap:8px">
          <button class="btn duplicate-cancel">${duplicateText("Annuler", "Cancel")}</button>
          <button class="btn btn-primary duplicate-confirm">${duplicateText("Continuer", "Continue")}</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    overlay.querySelector("#duplicate-apply-all").addEventListener("change", event => {
      if (event.target.value) overlay.querySelectorAll(".duplicate-action").forEach(select => { select.value = event.target.value; });
    });
    overlay.querySelector(".duplicate-cancel").addEventListener("click", () => {
      overlay.remove();
      reject(new Error(duplicateText("Ajout annulé", "Submission cancelled")));
    });
    overlay.querySelector(".duplicate-confirm").addEventListener("click", () => {
      const decisions = Array.from(overlay.querySelectorAll(".duplicate-action")).map(select => {
        const item = conflicts.find(candidate => candidate.id === select.dataset.sourceId);
        const diskPaths = item.conflicts.filter(conflict => conflict.type === "destination").map(conflict => conflict.path);
        return { source_id: item.id, action: select.value, diskPaths };
      });
      const overwrites = decisions.filter(decision => decision.action === "download" && decision.diskPaths.length).flatMap(decision => decision.diskPaths);
      if (overwrites.length && !confirm(`${duplicateText("Ces fichiers seront écrasés :", "These files will be overwritten:")}\n\n${overwrites.join("\n")}`)) return;
      decisions.forEach(decision => {
        decision.confirm_overwrite = decision.action === "download" && decision.diskPaths.length > 0;
        delete decision.diskPaths;
      });
      overlay.remove();
      resolve(decisions);
    });
  });
}

async function preflightAndCommit(formData) {
  const preflight = await duplicateApi("/api/downloads/preflight", { method: "POST", body: formData });
  const decisions = await chooseDuplicateActions(preflight);
  return duplicateApi(`/api/downloads/submissions/${preflight.submission_id}/commit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decisions }),
  });
}

let duplicateConflictBusy = false;
async function checkPendingDuplicateConflicts() {
  if (duplicateConflictBusy || document.querySelector(".duplicate-modal")) return;
  duplicateConflictBusy = true;
  try {
    const conflicts = await duplicateApi("/api/downloads/conflicts");
    if (!conflicts.length) return;
    const item = conflicts[0];
    const path = item.target_path || `${item.destination}/${item.name || ""}`;
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.innerHTML = `<div class="modal-box duplicate-modal" style="width:min(560px,calc(100vw - 24px))">
      <div class="modal-header"><div class="modal-header-title"><h3>${duplicateText("Fichier déjà présent", "File already exists")}</h3></div></div>
      <div style="padding:20px"><p>${duplicateText("Le nom final n’était disponible qu’après le traitement AllDebrid. Le téléchargement local est en attente.", "The final name became available after AllDebrid processing. The local download is waiting.")}</p>
      <div class="form-hint" style="margin-top:10px;overflow-wrap:anywhere">${escHtml(path)}</div></div>
      <div class="modal-footer" style="display:flex;justify-content:flex-end;gap:8px;flex-wrap:wrap">
        <button class="btn" data-action="ignore">${duplicateText("Ignorer", "Ignore")}</button>
        <button class="btn" data-action="download">${duplicateText("Télécharger quand même", "Download anyway")}</button>
        <button class="btn btn-primary" data-action="replace">${duplicateText("Remplacer", "Replace")}</button>
      </div></div>`;
    document.body.appendChild(overlay);
    await new Promise(resolve => {
      overlay.querySelectorAll("[data-action]").forEach(button => button.addEventListener("click", async () => {
        const action = button.dataset.action;
        let confirmed = false;
        if (action === "download") {
          confirmed = confirm(`${duplicateText("Confirmer l’écrasement de", "Confirm overwrite of")}\n${path}`);
          if (!confirmed) return;
        }
        try {
          await duplicateApi(`/api/downloads/conflicts/${item.id}/resolve`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action, confirm_overwrite: confirmed }),
          });
          overlay.remove();
          resolve();
        } catch (error) {
          showToast(t("error_prefix") + error.message, "error");
        }
      }));
    });
  } catch (error) {
    console.warn("Duplicate conflict check failed", error);
  } finally {
    duplicateConflictBusy = false;
  }
}

async function removeDownload(id) {
  try { await API.del(`/api/downloads/${id}`); }
  catch (e) { showToast(t("error_prefix") + e.message, "error"); }
}

async function pauseDownload(id) {
  try { await API.post(`/api/downloads/${id}/pause`, {}); }
  catch (e) { showToast(t("error_prefix") + e.message, "error"); }
}

async function resumeDownload(id) {
  try { await API.post(`/api/downloads/${id}/resume`, {}); }
  catch (e) { showToast(t("error_prefix") + e.message, "error"); }
}

async function bulkAction(action) {
  try {
    await API.post("/api/downloads/actions", { action });
  }
  catch (e) { showToast(t("error_prefix") + e.message, "error"); }
}

async function removeAllDownloads() {
  if (!confirm(t("confirm_remove_all"))) return;
  try {
    await API.post("/api/downloads/actions", { action: "remove_all" });
    showToast(t("all_removed"), "ok");
  } catch (e) { showToast(t("error_prefix") + e.message, "error"); }
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
  if (sub) sub.textContent = t("login_subtitle");
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
      errEl.textContent = data.detail || t("login_invalid");
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
      if (sub) sub.innerHTML = t("login_otp_step") + ' <a href="#" onclick="resetLoginForm();return false" style="display:block;margin-top:6px;font-size:12px">' + t("login_switch_account") + '</a>';
      _loginBusy = false;
      return;
    }

    // Success
    _loginOtpRequired = false;
    _loginBusy = false;
    loginSuccess(data.token);
  } catch {
    errEl.textContent = t("login_server_error");
    errEl.classList.remove("hidden");
    _loginBusy = false;
  }
}

async function doSetupAdmin() {
  const username = document.getElementById("setup-username").value.trim();
  const password = document.getElementById("setup-password").value;
  const confirm  = document.getElementById("setup-password-confirm").value;
  const errEl    = document.getElementById("setup-error");

  if (!username) { errEl.textContent = t("setup_username_required"); errEl.classList.remove("hidden"); return; }
  if (password.length < 6) { errEl.textContent = t("setup_password_min"); errEl.classList.remove("hidden"); return; }
  if (password !== confirm) { errEl.textContent = t("setup_password_mismatch"); errEl.classList.remove("hidden"); return; }

  try {
    const resp = await fetch("/api/auth/setup-admin", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!resp.ok) {
      const data = await resp.json();
      errEl.textContent = data.detail || t("settings_error");
      errEl.classList.remove("hidden");
      return;
    }
    const data = await resp.json();
    showToast(t("setup_success"), "ok");
    loginSuccess(data.token);
  } catch {
    errEl.textContent = t("login_server_error");
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
  if (sub) sub.textContent = t("login_subtitle");
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
      addUnifiedSources();
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

function updateMediaNavLabel(provider) {
  const label = provider === "jellyfin" ? "Jellyfin" : "Plex";
  document.querySelectorAll("[data-media-nav-label]").forEach((el) => { el.textContent = label; });
}

// ---- Initial load ----

async function loadInitial() {
  try {
    const [downloads, torrents, cfg] = await Promise.all([
      API.get("/api/downloads/"),
      API.get("/api/torrents/"),
      API.get("/api/settings/"),
    ]);
    renderDownloads(downloads);
    renderTorrents(torrents);

    const destInput = document.getElementById("dest-path");
    if (!destInput.value && cfg.default_destination) {
      setDestinationValue("dest-path", cfg.default_destination);
    }
    updateMediaNavLabel(cfg.media_provider);
  } catch {}

  loadPackages();
  loadHistory();
  loadDownloadDashboard();
}

// ---- Start app (called ONLY after auth is confirmed) ----

function startApp() {
  if (_appStarted) return;
  _appStarted = true;

  loadInitial();

  let _lastHistoryLoad = 0;
  let _prevCompleteIds = new Set();
  WS.on("downloads_update", (data, msg) => {
    renderDownloads(data);
    if (msg && msg.packages) {
      renderPackages(msg.packages);
    }
    if (msg && msg.torrents) {
      renderTorrents(msg.torrents);
    }
    // Reload history immediately if a new download completed, otherwise every 10s
    const now = Date.now();
    const curCompleteIds = new Set(data.filter(d => d.status === "complete" || d.status === "failed").map(d => d.id));
    let newCompletion = false;
    for (const id of curCompleteIds) {
      if (!_prevCompleteIds.has(id)) { newCompletion = true; break; }
    }
    _prevCompleteIds = curCompleteIds;
    const historyVisible = !document.getElementById("history-section").classList.contains("hidden");
    const safeToRefresh = !historyVisible || !historyInteractionInProgress();
    if ((newCompletion || now - _lastHistoryLoad > 30000) && safeToRefresh) {
      _lastHistoryLoad = now;
      loadHistory(true);
    }
  });
  WS.on("connection_status", () => renderRuntimeAlert());
  WS.init();
  setTimeout(checkRuntimeStatus, 2500);
  setInterval(checkRuntimeStatus, 30000);
  checkPendingDuplicateConflicts();
  setInterval(checkPendingDuplicateConflicts, 4000);

  if (typeof initAccountButton === "function") initAccountButton();
}

// ---- Boot ----

checkAuth();
