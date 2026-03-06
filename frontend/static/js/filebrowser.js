// File browser modal
const FileBrowser = (() => {
  let currentPath = "/";
  let selectedPath = "";
  let onSelectCallback = null;

  async function browse(path) {
    currentPath = path;
    const list = document.getElementById("fb-list");
    const crumbs = document.getElementById("fb-breadcrumbs");
    const pathDisplay = document.getElementById("fb-current-path");

    list.innerHTML = '<div class="fb-loading">Chargement...</div>';

    try {
      const resp = await API.get(`/api/files/browse?path=${encodeURIComponent(path)}`);

      // Breadcrumbs
      crumbs.innerHTML = resp.breadcrumbs
        .map((b, i) => {
          const isLast = i === resp.breadcrumbs.length - 1;
          const sep = i > 0 ? '<span class="breadcrumb-sep"> / </span>' : "";
          return `${sep}<span class="breadcrumb-item${isLast ? " active" : ""}"
            onclick="FileBrowser._browse('${escHtml(b.path)}')">${escHtml(b.name)}</span>`;
        })
        .join("");

      selectedPath = resp.path;
      pathDisplay.textContent = resp.path;

      // Directory list
      if (resp.error) {
        list.innerHTML = `<div class="fb-empty">${escHtml(resp.error)}</div>`;
        return;
      }

      if (resp.directories.length === 0) {
        list.innerHTML = '<div class="fb-empty">Aucun sous-dossier</div>';
        return;
      }

      list.innerHTML = resp.directories
        .map(
          (d) => `
          <div class="fb-item" onclick="FileBrowser._select('${escHtml(d.path)}')">
            <span class="fb-icon">📁</span>
            <span class="fb-name" title="${escHtml(d.path)}">${escHtml(d.name)}</span>
            ${d.has_children ? '<span class="fb-arrow">›</span>' : ""}
          </div>`
        )
        .join("");
    } catch (e) {
      list.innerHTML = `<div class="fb-empty">Erreur : ${escHtml(String(e))}</div>`;
    }
  }

  function escHtml(str) {
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
    _select(path) {
      // Single click: highlight + update selected path
      selectedPath = path;
      document.getElementById("fb-current-path").textContent = path;
      document.querySelectorAll(".fb-item").forEach((el) => el.classList.remove("selected"));
      event.currentTarget.classList.add("selected");
    },
  };
})();

// Click on a directory navigates into it; click again to select or use button
// Override _select to navigate on single click
FileBrowser._select = function (path) {
  FileBrowser._browse(path);
};

function openFileBrowser() { FileBrowser.open((path) => {
  document.getElementById("dest-path").value = path;
  const label = document.getElementById("dest-label");
  label.textContent = path;
  document.querySelector(".btn-dest").classList.add("selected");
}); }

function closeFilerBrowser() { FileBrowser.close(); }
function selectCurrentPath() { FileBrowser.confirm(); }
