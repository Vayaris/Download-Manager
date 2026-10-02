const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../frontend/static/js/appearance-bootstrap.js'), 'utf8');

function browser(initial = {}, dark = false, unavailable = false) {
  const values = new Map(Object.entries(initial));
  const root = { dataset: {}, style: {} };
  const meta = {};
  let listener;
  const system = { matches: dark, addEventListener: (_, fn) => { listener = fn; } };
  const context = {
    document: { documentElement: root, querySelector: () => meta },
    localStorage: {
      getItem: key => { if (unavailable) throw Error('blocked'); return values.get(key) || null; },
      setItem: (key, value) => { if (unavailable) throw Error('blocked'); values.set(key, value); },
    },
    window: { matchMedia: () => system, dispatchEvent: () => {} },
    Event: class {},
  };
  vm.runInNewContext(source, context);
  return { root, meta, values, appearance: context.window.DMAppearance,
    systemChange(value) { system.matches = value; listener(); } };
}

test('legacy light/dark choices migrate without changing appearance', () => {
  for (const mode of ['light', 'dark']) {
    const state = browser({ dm_theme: mode }, mode === 'light');
    assert.equal(state.root.dataset.theme, mode);
    assert.equal(state.root.dataset.themeMode, mode);
    assert.equal(state.root.dataset.palette, 'ambre');
    assert.equal(state.values.get('dm_theme_mode'), mode);
  }
});

test('system mode follows OS changes and explicit mode stops following', () => {
  const state = browser();
  assert.equal(state.root.dataset.themeMode, 'system');
  state.systemChange(true);
  assert.equal(state.root.dataset.theme, 'dark');
  state.appearance.setMode('light');
  state.systemChange(true);
  assert.equal(state.root.dataset.theme, 'light');
  assert.equal(state.values.get('dm_theme'), 'light');
});

test('palettes persist independently and update PWA color before paint', () => {
  const state = browser({ dm_theme_mode: 'dark', dm_palette: 'ocean' });
  assert.equal(state.meta.content, '#10191b');
  state.appearance.setPalette('foret');
  assert.equal(state.values.get('dm_palette'), 'foret');
  assert.equal(state.root.dataset.theme, 'dark');
  assert.equal(state.meta.content, '#121a14');
  const reloaded = browser(Object.fromEntries(state.values));
  assert.equal(reloaded.root.dataset.palette, 'foret');
  assert.equal(reloaded.root.dataset.themeMode, 'dark');
});

test('invalid or unavailable browser storage has a usable default', () => {
  for (const state of [browser({ dm_palette: 'invalid', dm_theme_mode: 'invalid' }), browser({}, false, true)]) {
    assert.equal(state.root.dataset.palette, 'ambre');
    assert.equal(state.root.dataset.theme, 'light');
  }
});

function explorer(fetch) {
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      innerHTML: '', value: '', textContent: '', disabled: false, style: {},
      classList: { toggle() {}, add() {}, remove() {} },
      querySelectorAll: () => [], addEventListener() {},
    });
    return elements.get(id);
  }
  const timers = new Map();
  let timer = 0;
  const context = vm.createContext({
    document: { getElementById: element, querySelectorAll: () => [] },
    fetch, AbortController, URLSearchParams,
    getAuthToken: () => '', t: key => key, showToast() {},
    setTimeout(fn) { timers.set(++timer, fn); return timer; },
    clearTimeout(id) { timers.delete(id); },
  });
  vm.runInContext(fs.readFileSync(require('node:path').join(__dirname, '../frontend/static/js/filebrowser.js'), 'utf8'), context);
  return { browser: vm.runInContext('FileBrowser', context), element, timers };
}

test('obsolete folder responses cannot overwrite a newer navigation', async () => {
  let release;
  const oldJson = new Promise(resolve => { release = resolve; });
  const state = explorer(async url => ({ ok: true, json: () => url.includes('slow') ? oldJson : Promise.resolve({ path: '/fast', selectable: true, directories: [], breadcrumbs: [] }) }));
  const slow = state.browser._browse('/slow');
  assert.match(state.element('fb-list').innerHTML, /fb-loading/);
  assert.equal(state.element('fb-select-button').disabled, true);
  await new Promise(resolve => setImmediate(resolve));
  await state.browser._browse('/fast');
  release({ path: '/slow', selectable: true, directories: [], breadcrumbs: [] });
  await slow;
  assert.equal(state.browser.getCurrentPath(), '/fast');
  assert.equal(state.element('fb-path-input').value, '/fast');
});

test('closing the explorer cancels polling and ignores a late result', async () => {
  const state = explorer(async () => ({ ok: true, json: async () => ({ loading: true, elapsed_seconds: 7 }) }));
  await state.browser._browse('/slow');
  assert.match(state.element('fb-list').innerHTML, /v3_storage_waiting/);
  assert.equal(state.timers.size, 1);
  state.browser.close();
  assert.equal(state.timers.size, 0);
});
