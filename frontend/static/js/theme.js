// Appearance preferences are local to each browser and applied before page paint.
function getUIStyle() {
  return document.documentElement.getAttribute("data-ui-style") === "modern" ? "modern" : "classic";
}

function updateThemeColor() {
  var meta = document.querySelector('meta[name="theme-color"]');
  if (!meta) return;
  if (window.DMAppearance) window.DMAppearance.apply();
}

function applyUIStyle(style) {
  var next = style === "classic" ? "classic" : "modern";
  document.documentElement.setAttribute("data-ui-style", next);
  localStorage.setItem("dm_ui_style", next);
  var select = document.getElementById("acct-ui-style-select");
  if (select) select.value = next;
  updateThemeColor();
  return next;
}

async function setUIStyle(style) {
  var previous = getUIStyle();
  var next = applyUIStyle(style);
  if (typeof apiFetch === "undefined") return;
  try {
    await apiFetch.put("/api/auth/preferences", { ui_style: next });
  } catch (error) {
    applyUIStyle(previous);
    if (typeof showToast === "function") showToast(error.message, "error");
  }
}

function syncAppearanceControls() {
  const root = document.documentElement;
  document.querySelectorAll('.theme-toggle').forEach(btn => {
    const sun = btn.querySelector('.icon-sun'), moon = btn.querySelector('.icon-moon');
    if (sun) sun.style.display = root.dataset.theme === 'light' ? 'block' : 'none';
    if (moon) moon.style.display = root.dataset.theme === 'dark' ? 'block' : 'none';
    btn.setAttribute('aria-pressed', String(root.dataset.theme === 'dark'));
  });
  [['appearance-mode', root.dataset.themeMode], ['appearance-palette', root.dataset.palette], ['appearance-style', getUIStyle()]].forEach(([id, value]) => { const el = document.getElementById(id); if (el) el.value = value; });
}
function toggleTheme() { DMAppearance.setMode(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'); }
window.addEventListener('dm-appearance-change', syncAppearanceControls);
syncAppearanceControls();
