// File browser modal with mkdir support
const FileBrowser = (() => {
  let currentPath = "/";
  let selectedPath = "";
  let onSelectCallback = null;

  // ---- Path history (localStorage, max 10) ----
  const HISTORY_KEY = "dm_path_history";
  const HISTORY_MAX = 10;

  function _saveHistory(path) {
    if (!path || path === "/") return;
    try {
      let h = _getHistory();
      h = [path, ...h.filter(p => p !== path)].slice(0, HISTORY_MAX);
      localStorage.setItem(HISTORY_KEY, JSON.stringify(h));
    } catch {}
  }

  function _getHistory() {
    try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]"); } catch { return []; }
  }

  function _renderHistory() {
    const container = document.getElementById("fb-history");
    const list = document.getElementById("fb-history-list");
    if (!container || !list) return;
    const h = _getHistory();
    if (h.length === 0) { container.classList.add("hidden"); return; }
    container.classList.remove("hidden");
    list.innerHTML = h.map(p =>
      `<div class="fb-history-item" onclick="FileBrowser._browse('${_esc(p)}')" title="${_esc(p)}">
        <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
        <span class="fb-history-path">${_esc(p)}</span>
      </div>`
    ).join("");
    if (typeof applyTranslations === "function") {
      container.querySelectorAll("[data-i18n]").forEach(el => { el.textContent = t(el.dataset.i18n); });
    }
  }

  async function browse(path) {
    currentPath = path;
    const list = document.getElementById("fb-list");
    const crumbs = document.getElementById("fb-breadcrumbs");

    list.innerHTML = '<div class="fb-loading">' + t("fb_loading") + '</div>';

    try {
      const resp = await API.get(`/api/files/browse?path=${encodeURIComponent(path)}`);

      // Breadcrumbs
      crumbs.innerHTML = resp.breadcrumbs
        .map((b, i) => {
          const isLast = i === resp.breadcrumbs.length - 1;
          const sep = i > 0 ? '<span class="breadcrumb-sep"> / </span>' : "";
          return `${sep}<span class="breadcrumb-item${isLast ? " active" : ""}"
            onclick="FileBrowser._browse('${_esc(b.path)}')">${_esc(b.name)}</span>`;
        })
        .join("");

      selectedPath = resp.path;
      const pathText = document.getElementById("fb-path-text");
      if (pathText) pathText.textContent = resp.path;

      // Directory list
      if (resp.error) {
        list.innerHTML = `<div class="fb-empty">${_esc(resp.error)}</div>`;
        return;
      }

      if (resp.directories.length === 0) {
        list.innerHTML = '<div class="fb-empty">' + t("fb_empty") + '</div>';
        return;
      }

      list.innerHTML = resp.directories
        .map(
          (d) => `
          <div class="fb-item" onclick="FileBrowser._browse('${_esc(d.path)}')">
            <span class="fb-icon">${ICONS ? ICONS.folder : '📁'}</span>
            <span class="fb-name" title="${_esc(d.path)}">${_esc(d.name)}</span>
            ${d.has_children ? '<span class="fb-arrow">›</span>' : ""}
          </div>`
        )
        .join("");
    } catch (e) {
      list.innerHTML = `<div class="fb-empty">${t("fb_error")}${_esc(String(e))}</div>`;
    }
  }

  function _esc(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  return {
    open(callback, startPath) {
      onSelectCallback = callback;
      const modal = document.getElementById("filebrowser-modal");
      modal.classList.remove("hidden");
      hideMkdirInput();
      _renderHistory();
      // Determine starting path
      const initial = startPath || _getDefaultDest() || "/";
      browse(initial);
    },
    close() {
      const modal = document.getElementById("filebrowser-modal");
      modal.classList.add("hidden");
      // Reset z-index
      modal.style.zIndex = "";
    },
    confirm() {
      _saveHistory(selectedPath);
      if (onSelectCallback) onSelectCallback(selectedPath);
      this.close();
    },
    // Elevate z-index so file browser appears above other modals (e.g. package modal)
    elevate() {
      document.getElementById("filebrowser-modal").style.zIndex = "2000";
    },
    _browse: browse,
    getCurrentPath() { return currentPath; },
  };
})();

function _getDefaultDest() {
  // Try to get default destination from existing inputs
  const destInput = document.getElementById("dest-path");
  if (destInput && destInput.value.trim()) return destInput.value.trim();
  // For settings page
  const defaultDest = document.getElementById("default-dest");
  if (defaultDest && defaultDest.value.trim()) return defaultDest.value.trim();
  return "";
}

function openFileBrowser() {
  FileBrowser.open((path) => {
    document.getElementById("dest-path").value = path;
    const label = document.getElementById("dest-label");
    label.textContent = path;
    document.getElementById("dest-selector").classList.add("selected");
  });
}

function closeFilerBrowser() { FileBrowser.close(); }
function selectCurrentPath() { FileBrowser.confirm(); }

// ---- Mkdir ----

function showMkdirInput() {
  document.getElementById("mkdir-input-wrap").classList.remove("hidden");
  document.getElementById("mkdir-name").value = "";
  document.getElementById("mkdir-name").focus();
}

function hideMkdirInput() {
  document.getElementById("mkdir-input-wrap").classList.add("hidden");
}

async function createFolder() {
  const name = document.getElementById("mkdir-name").value.trim();
  if (!name) { showToast(t("fb_folder_required"), "error"); return; }

  const currentPath = FileBrowser.getCurrentPath();

  try {
    const resp = await API.post("/api/files/mkdir", { path: currentPath, name: name });
    showToast(t("fb_folder_created", { name }), "ok");
    hideMkdirInput();
    // Refresh and navigate to new folder
    FileBrowser._browse(resp.path);
  } catch (e) {
    let msg = t("settings_error");
    try { msg = JSON.parse(e.message).detail; } catch { msg = e.message; }
    showToast(msg, "error");
  }
}
