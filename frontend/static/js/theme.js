// Theme — read from DOM, persist to localStorage
function toggleTheme() {
  var html = document.documentElement;
  var current = html.getAttribute('data-theme');
  var next = (current === 'light') ? 'dark' : 'light';

  html.setAttribute('data-theme', next);
  localStorage.setItem('dm_theme', next);

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
  var theme = document.documentElement.getAttribute('data-theme') || 'dark';
  var btns = document.querySelectorAll('.theme-toggle');
  for (var i = 0; i < btns.length; i++) {
    var sun = btns[i].querySelector('.icon-sun');
    var moon = btns[i].querySelector('.icon-moon');
    if (sun) sun.style.display = (theme === 'light') ? 'block' : 'none';
    if (moon) moon.style.display = (theme === 'dark') ? 'block' : 'none';
  }
})();
