const FileBrowser = (() => {
  let currentPath = "/";
  let selectedPath = "";
  let currentDirectories = [];
  let preferences = { favorites: [], recents: [] };
  let onSelectCallback = null;
  let browseController = null;
  let dragState = null;

  const folderIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>';

  function esc(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function authHeaders(json = false) {
    const headers = {};
    const token = getAuthToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    if (json) headers["Content-Type"] = "application/json";
    return headers;
  }

  async function request(url, options = {}) {
    const response = await fetch(url, options);
    if (response.status === 401) {
      if (window.apiFetch && apiFetch._handleUnauth) apiFetch._handleUnauth();
      throw new Error("Unauthorized");
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    return data;
  }

  function isFavorite(path) {
    return preferences.favorites.some(item => item.path === path);
  }

  function renderBreadcrumbs(items) {
    const container = document.getElementById("fb-breadcrumbs");
    container.innerHTML = items.map((item, index) => `
      ${index ? '<span class="breadcrumb-sep">/</span>' : ""}
      <button type="button" class="breadcrumb-item${index === items.length - 1 ? " active" : ""}"
        data-fb-path="${esc(item.path)}">${esc(item.name)}</button>
    `).join("");
    container.querySelectorAll("[data-fb-path]").forEach(button => {
      button.addEventListener("click", () => browse(button.dataset.fbPath));
    });
  }

  function renderDirectories(filter = "") {
    const list = document.getElementById("fb-list");
    const needle = filter.trim().toLocaleLowerCase();
    const directories = currentDirectories.filter(item =>
      !needle || item.name.toLocaleLowerCase().includes(needle)
    );
    if (!directories.length) {
      list.innerHTML = `<div class="fb-empty">${esc(needle ? t("fb_search_empty") : t("fb_empty"))}</div>`;
      return;
    }
    list.innerHTML = directories.map(item => `
      <div class="fb-item" data-fb-open="${esc(item.path)}">
        <span class="fb-folder-icon">${folderIcon}</span>
        <span class="fb-name" title="${esc(item.path)}">${esc(item.name)}</span>
        <button type="button" class="fb-star${isFavorite(item.path) ? " active" : ""}"
          data-fb-favorite="${esc(item.path)}" title="${esc(t(isFavorite(item.path) ? "fb_remove_favorite" : "fb_add_favorite"))}">
          ${isFavorite(item.path) ? "★" : "☆"}
        </button>
        <span class="fb-chevron">›</span>
      </div>
    `).join("");
    list.querySelectorAll("[data-fb-open]").forEach(row => {
      row.addEventListener("click", event => {
        if (!event.target.closest("[data-fb-favorite]")) browse(row.dataset.fbOpen);
      });
    });
    list.querySelectorAll("[data-fb-favorite]").forEach(button => {
      button.addEventListener("click", event => {
        event.stopPropagation();
        toggleFavorite(button.dataset.fbFavorite);
      });
    });
  }

  function renderFavorites() {
    const list = document.getElementById("fb-favorites-list");
    if (!preferences.favorites.length) {
      list.innerHTML = `<div class="fb-side-empty">${esc(t("fb_favorites_empty"))}</div>`;
      return;
    }
    list.innerHTML = preferences.favorites.map(item => `
      <div class="fb-place${item.available ? "" : " unavailable"}" data-favorite-path="${esc(item.path)}">
        <button type="button" class="fb-place-main" data-fb-open="${esc(item.path)}" ${item.available ? "" : "disabled"}>
          <span class="fb-place-icon">${folderIcon}</span>
          <span class="fb-place-copy">
            <strong>${esc(item.name)}</strong>
            <em title="${esc(item.path)}">${esc(item.storage_label)}${item.available ? "" : ` · ${t("fb_unavailable")}`}</em>
          </span>
        </button>
        <button type="button" class="fb-place-remove" data-fb-remove="${esc(item.path)}" title="${esc(t("fb_remove_favorite"))}">×</button>
        <button type="button" class="fb-drag-handle" aria-label="${esc(t("fb_reorder_favorite"))}">⋮⋮</button>
      </div>
    `).join("");
    list.querySelectorAll("[data-fb-open]").forEach(button => {
      button.addEventListener("click", () => browse(button.dataset.fbOpen));
    });
    list.querySelectorAll("[data-fb-remove]").forEach(button => {
      button.addEventListener("click", () => removeFavorite(button.dataset.fbRemove));
    });
    bindFavoriteDrag(list);
  }

  function renderRecents() {
    const list = document.getElementById("fb-recents-list");
    if (!preferences.recents.length) {
      list.innerHTML = `<div class="fb-side-empty">${esc(t("fb_recent_empty"))}</div>`;
      return;
    }
    list.innerHTML = preferences.recents.map(item => `
      <button type="button" class="fb-recent${item.available ? "" : " unavailable"}"
        data-fb-open="${esc(item.path)}" ${item.available ? "" : "disabled"} title="${esc(item.path)}">
        <span class="fb-place-icon">${folderIcon}</span>
        <span class="fb-place-copy">
          <strong>${esc(item.name)}</strong>
          <em>${esc(item.storage_label)}${item.available ? "" : ` · ${t("fb_unavailable")}`}</em>
        </span>
      </button>
    `).join("");
    list.querySelectorAll("[data-fb-open]").forEach(button => {
      button.addEventListener("click", () => browse(button.dataset.fbOpen));
    });
  }

  function renderPreferences(renderDirectoryList = true) {
    renderFavorites();
    renderRecents();
    const currentStar = document.getElementById("fb-current-favorite");
    if (currentStar) {
      currentStar.disabled = !selectedPath;
      currentStar.classList.toggle("active", isFavorite(currentPath));
      currentStar.textContent = isFavorite(currentPath) ? "★" : "☆";
      currentStar.title = t(isFavorite(currentPath) ? "fb_remove_favorite" : "fb_add_favorite");
    }
    if (renderDirectoryList) {
      renderDirectories(document.getElementById("fb-search")?.value || "");
    }
  }

  async function loadPreferences() {
    try {
      preferences = await request("/api/files/preferences", { headers: authHeaders() });
      renderPreferences();
    } catch (error) {
      showToast(t("fb_preferences_error") + error.message, "error");
    }
  }

  async function browse(path, refresh = false) {
    const target = String(path || "/").trim() || "/";
    currentPath = target;
    const list = document.getElementById("fb-list");
    list.innerHTML = `<div class="fb-loading"><span class="fb-spinner"></span>${esc(t("fb_loading"))}</div>`;
    if (browseController) browseController.abort();
    browseController = new AbortController();
    try {
      const query = new URLSearchParams({ path: target });
      if (refresh) query.set("refresh", "true");
      const response = await fetch(`/api/files/browse?${query}`, {
        headers: authHeaders(),
        signal: browseController.signal,
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      currentPath = data.path || target;
      selectedPath = data.selectable ? currentPath : "";
      currentDirectories = data.directories || [];
      renderBreadcrumbs(data.breadcrumbs || []);
      document.getElementById("fb-path-input").value = currentPath;
      document.getElementById("fb-path-text").textContent = currentPath;
      document.getElementById("fb-select-button").disabled = !data.selectable;
      document.getElementById("fb-search").value = "";
      if (data.error) {
        list.innerHTML = `<div class="fb-empty fb-error-state"><span>${esc(data.error)}</span><button type="button" class="btn btn-sm" id="fb-retry">${esc(t("fb_retry"))}</button></div>`;
        document.getElementById("fb-retry").addEventListener("click", () => browse(currentPath, true));
      } else {
        renderDirectories();
      }
      renderPreferences(!data.error);
    } catch (error) {
      if (error.name === "AbortError") return;
      list.innerHTML = `<div class="fb-empty fb-error-state"><span>${esc(t("fb_error") + error.message)}</span><button type="button" class="btn btn-sm" id="fb-retry">${esc(t("fb_retry"))}</button></div>`;
      document.getElementById("fb-retry")?.addEventListener("click", () => browse(currentPath, true));
    }
  }

  async function toggleFavorite(path) {
    if (isFavorite(path)) return removeFavorite(path);
    try {
      await request("/api/files/favorites", {
        method: "POST", headers: authHeaders(true), body: JSON.stringify({ path }),
      });
      await loadPreferences();
    } catch (error) {
      showToast(t("error_prefix") + error.message, "error");
    }
  }

  async function removeFavorite(path) {
    try {
      await request(`/api/files/favorites?path=${encodeURIComponent(path)}`, {
        method: "DELETE", headers: authHeaders(),
      });
      await loadPreferences();
    } catch (error) {
      showToast(t("error_prefix") + error.message, "error");
    }
  }

  async function saveFavoriteOrder(list) {
    const paths = Array.from(list.querySelectorAll("[data-favorite-path]"))
      .map(item => item.dataset.favoritePath);
    try {
      await request("/api/files/favorites/reorder", {
        method: "PUT", headers: authHeaders(true), body: JSON.stringify({ paths }),
      });
      preferences.favorites.sort((a, b) => paths.indexOf(a.path) - paths.indexOf(b.path));
    } catch (error) {
      showToast(t("error_prefix") + error.message, "error");
      await loadPreferences();
    }
  }

  function bindFavoriteDrag(list) {
    list.querySelectorAll(".fb-drag-handle").forEach(handle => {
      handle.addEventListener("pointerdown", event => {
        const item = handle.closest("[data-favorite-path]");
        dragState = { item, pointerId: event.pointerId };
        item.classList.add("dragging");
        handle.setPointerCapture(event.pointerId);
        event.preventDefault();
      });
      handle.addEventListener("pointermove", event => {
        if (!dragState || dragState.pointerId !== event.pointerId) return;
        const over = document.elementFromPoint(event.clientX, event.clientY)?.closest("[data-favorite-path]");
        if (!over || over === dragState.item || over.parentElement !== list) return;
        const rect = over.getBoundingClientRect();
        list.insertBefore(dragState.item, event.clientY < rect.top + rect.height / 2 ? over : over.nextSibling);
      });
      const finish = event => {
        if (!dragState || dragState.pointerId !== event.pointerId) return;
        dragState.item.classList.remove("dragging");
        dragState = null;
        saveFavoriteOrder(list);
      };
      handle.addEventListener("pointerup", finish);
      handle.addEventListener("pointercancel", finish);
    });
  }

  async function confirm() {
    if (!selectedPath) return;
    try {
      await request("/api/files/recents", {
        method: "POST", headers: authHeaders(true), body: JSON.stringify({ path: selectedPath }),
      });
    } catch {}
    if (onSelectCallback) onSelectCallback(selectedPath);
    close();
  }

  function close() {
    browseController?.abort();
    document.getElementById("filebrowser-modal").classList.add("hidden");
    document.getElementById("filebrowser-modal").style.zIndex = "";
  }

  function setMobilePanel(panel) {
    document.getElementById("filebrowser-modal").dataset.fbPanel = panel;
    document.querySelectorAll("[data-fb-panel-button]").forEach(button => {
      button.classList.toggle("active", button.dataset.fbPanelButton === panel);
    });
  }

  return {
    open(callback, startPath) {
      onSelectCallback = callback;
      localStorage.removeItem("dm_path_history");
      const modal = document.getElementById("filebrowser-modal");
      modal.classList.remove("hidden");
      setMobilePanel("explorer");
      hideMkdirInput();
      loadPreferences();
      browse(startPath || _getDefaultDest() || "/");
    },
    close,
    confirm,
    elevate() { document.getElementById("filebrowser-modal").style.zIndex = "2000"; },
    _browse: browse,
    refresh() { browse(currentPath, true); },
    goToPath() { browse(document.getElementById("fb-path-input").value); },
    filter(value) { renderDirectories(value); },
    toggleCurrentFavorite() { toggleFavorite(currentPath); },
    setMobilePanel,
    getCurrentPath() { return currentPath; },
  };
})();

function _getDefaultDest() {
  const destInput = document.getElementById("dest-path-text") || document.getElementById("dest-path");
  if (destInput && destInput.value.trim()) return destInput.value.trim();
  const defaultDest = document.getElementById("default-dest");
  if (defaultDest && defaultDest.value.trim()) return defaultDest.value.trim();
  return "";
}

function setDestinationValue(hiddenId, path) {
  const value = (path || "").trim();
  const hidden = document.getElementById(hiddenId);
  if (hidden) hidden.value = value;
  const input = document.querySelector(`[data-dest-hidden="${hiddenId}"]`);
  if (input) input.value = value;
  const selector = hiddenId === "dest-path"
    ? document.getElementById("dest-selector")
    : document.getElementById(hiddenId.replace("-path", "-selector"));
  if (selector) selector.classList.toggle("selected", !!value);
  const label = hiddenId === "dest-path"
    ? document.getElementById("dest-label")
    : document.getElementById(hiddenId.replace("-path", "-label"));
  if (label) label.textContent = value || t("dest_choose");
}

function getDestinationValue(hiddenId) {
  const input = document.querySelector(`[data-dest-hidden="${hiddenId}"]`);
  const value = input ? input.value.trim() : "";
  if (value) setDestinationValue(hiddenId, value);
  const hidden = document.getElementById(hiddenId);
  return (hidden ? hidden.value : value).trim();
}

function initDestinationInputs() {
  document.querySelectorAll("[data-dest-hidden]").forEach(input => {
    const hiddenId = input.dataset.destHidden;
    input.addEventListener("input", () => setDestinationValue(hiddenId, input.value));
    input.addEventListener("blur", () => setDestinationValue(hiddenId, input.value));
    input.addEventListener("keydown", event => {
      if (event.key === "Enter") {
        event.preventDefault();
        setDestinationValue(hiddenId, input.value);
      }
    });
  });
}

function openFileBrowser() {
  FileBrowser.open(path => setDestinationValue("dest-path", path));
}

function closeFilerBrowser() { FileBrowser.close(); }
function selectCurrentPath() { FileBrowser.confirm(); }

function showMkdirInput() {
  const wrap = document.getElementById("mkdir-input-wrap");
  const input = document.getElementById("mkdir-name");
  wrap.classList.remove("hidden");
  input.value = "";
  input.setAttribute("dir", "ltr");
  setTimeout(() => input.focus(), 0);
}

function hideMkdirInput() {
  document.getElementById("mkdir-input-wrap").classList.add("hidden");
}

async function createFolder() {
  const input = document.getElementById("mkdir-name");
  const name = String(input.value || "").trim();
  if (!name) { showToast(t("fb_folder_required"), "error"); return; }
  try {
    const response = await API.post("/api/files/mkdir", { path: FileBrowser.getCurrentPath(), name });
    showToast(t("fb_folder_created", { name }), "ok");
    hideMkdirInput();
    FileBrowser._browse(response.path, true);
  } catch (error) {
    showToast(t("error_prefix") + error.message, "error");
  }
}

initDestinationInputs();
