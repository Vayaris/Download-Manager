// File browser modal with mkdir support
const FileBrowser = (() => {
  let currentPath = "/";
  let selectedPath = "";
  let onSelectCallback = null;

  async function browse(path) {
    currentPath = path;
    const list = document.getElementById("fb-list");
    const crumbs = document.getElementById("fb-breadcrumbs");

    list.innerHTML = '<div class="fb-loading">Chargement...</div>';

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
        list.innerHTML = '<div class="fb-empty">Aucun sous-dossier</div>';
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
      list.innerHTML = `<div class="fb-empty">Erreur : ${_esc(String(e))}</div>`;
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
    open(callback) {
      onSelectCallback = callback;
      document.getElementById("filebrowser-modal").classList.remove("hidden");
      hideMkdirInput();
      browse("/");
    },
    close() {
      document.getElementById("filebrowser-modal").classList.add("hidden");
    },
    confirm() {
      if (onSelectCallback) onSelectCallback(selectedPath);
      this.close();
    },
    _browse: browse,
    getCurrentPath() { return currentPath; },
  };
})();

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
  if (!name) { showToast("Nom du dossier requis", "error"); return; }

  const currentPath = FileBrowser.getCurrentPath();

  try {
    const resp = await API.post("/api/files/mkdir", { path: currentPath, name: name });
    showToast(`Dossier « ${name} » créé`, "ok");
    hideMkdirInput();
    // Refresh and navigate to new folder
    FileBrowser._browse(resp.path);
  } catch (e) {
    let msg = "Erreur";
    try { msg = JSON.parse(e.message).detail; } catch { msg = e.message; }
    showToast(msg, "error");
  }
}
