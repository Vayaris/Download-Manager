// Appearance preferences are local to each browser and applied before page paint.
function getUIStyle() {
  return document.documentElement.getAttribute("data-ui-style") === "modern" ? "modern" : "classic";
}

function updateThemeColor() {
  var meta = document.querySelector('meta[name="theme-color"]');
  if (!meta) return;
  var modern = getUIStyle() === "modern";
  var dark = document.documentElement.getAttribute("data-theme") === "dark";
  meta.setAttribute("content", modern ? (dark ? "#11110f" : "#171715") : (dark ? "#0d1110" : "#f5f3ed"));
}

function setUIStyle(style) {
  var next = style === "modern" ? "modern" : "classic";
  document.documentElement.setAttribute("data-ui-style", next);
  localStorage.setItem("dm_ui_style", next);
  var select = document.getElementById("acct-ui-style-select");
  if (select) select.value = next;
  updateThemeColor();
}

// Theme — read from DOM, persist to localStorage
function toggleTheme() {
  var html = document.documentElement;
  var current = html.getAttribute('data-theme');
  var next = (current === 'light') ? 'dark' : 'light';

  html.setAttribute('data-theme', next);
  localStorage.setItem('dm_theme', next);
  updateThemeColor();

  // Update icons
  var btns = document.querySelectorAll('.theme-toggle');
  for (var i = 0; i < btns.length; i++) {
    var sun = btns[i].querySelector('.icon-sun');
    var moon = btns[i].querySelector('.icon-moon');
    if (sun) sun.style.display = (next === 'light') ? 'block' : 'none';
    if (moon) moon.style.display = (next === 'dark') ? 'block' : 'none';
  }
}

// Init icons on page load
(function() {
  var theme = document.documentElement.getAttribute('data-theme') || 'light';
  var btns = document.querySelectorAll('.theme-toggle');
  for (var i = 0; i < btns.length; i++) {
    var sun = btns[i].querySelector('.icon-sun');
    var moon = btns[i].querySelector('.icon-moon');
    if (sun) sun.style.display = (theme === 'light') ? 'block' : 'none';
    if (moon) moon.style.display = (theme === 'dark') ? 'block' : 'none';
  }
  updateThemeColor();
})();
