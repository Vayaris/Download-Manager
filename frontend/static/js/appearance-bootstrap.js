// Runs in <head>, before styles and first paint. Browser-local preferences only.
(function () {
  const root = document.documentElement;
  function read(key) { try { return localStorage.getItem(key); } catch { return null; } }
  function write(key, value) { try { localStorage.setItem(key, value); } catch {} }
  const system = window.matchMedia('(prefers-color-scheme: dark)');
  let mode = read('dm_theme_mode');
  if (!['light', 'dark', 'system'].includes(mode)) {
    const legacy = read('dm_theme');
    mode = ['light', 'dark'].includes(legacy) ? legacy : 'system';
    write('dm_theme_mode', mode);
  }
  let palette = read('dm_palette');
  if (!['ambre', 'ocean', 'foret'].includes(palette)) palette = 'ambre';
  const colors = {ambre: ['#f2f0ea', '#11110f'], ocean: ['#eef4f4', '#10191b'], foret: ['#eff3ec', '#121a14']};
  function apply() {
    const dark = mode === 'dark' || (mode === 'system' && system.matches);
    root.dataset.theme = dark ? 'dark' : 'light';
    root.dataset.palette = palette;
    root.dataset.themeMode = mode;
    root.style.colorScheme = dark ? 'dark' : 'light';
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = colors[palette][dark ? 1 : 0];
    window.dispatchEvent(new Event('dm-appearance-change'));
  }
  window.DMAppearance = {
    apply,
    setMode(value) { if (['light', 'dark', 'system'].includes(value)) { mode=value; write('dm_theme_mode', mode); if (mode !== 'system') write('dm_theme', mode); apply(); } },
    setPalette(value) { if (colors[value]) { palette=value; write('dm_palette', value); apply(); } }
  };
  system.addEventListener('change', () => { if (mode === 'system') apply(); });
  apply();
})();
