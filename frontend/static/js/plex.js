// ============================================================
//  Plex library refresh page
// ============================================================

const API = apiFetch;
API._handleUnauth = showPlexLogin;

let _toastTimer = null;
let _plexOtpRequired = false;

function showToast(msg, type = "ok") {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = msg;
  el.className = `toast ${type}`;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.add("hidden"), 3500);
}

function setPlexPageBadge(state, text) {
  const badge = document.getElementById("plex-page-status-badge");
  const label = document.getElementById("plex-page-status-text");
  if (!badge || !label) return;
  badge.className = `conn-badge ${state}`;
  label.textContent = text;
}

function formatPlexRefreshTime(value) {
  if (!value) return t("plex_never_refreshed");
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

let _plexState = {
  enabled: false,
  connected: false,
  server: null,
  libraries: [],
  favoriteKeys: [],
  lastRefreshes: {},
  query: "",
  error: "",
};

function normalizePlexState(data) {
  data = data || {};
  const libraries = Array.isArray(data.libraries) ? data.libraries.map((library) => ({
    key: String(library.key || "").trim(),
    title: String(library.title || "").trim(),
    type: String(library.type || "").trim(),
  })).filter((library) => library.key && library.title) : [];
  const byKey = new Map(libraries.map((library) => [library.key, library]));
  const favoriteKeys = Array.isArray(data.favorite_keys) ? data.favorite_keys.map((key) => String(key || "").trim()).filter((key) => byKey.has(key)) : [];
  const favoriteSet = new Set(favoriteKeys);
  const sortedLibraries = libraries.slice().sort((a, b) => {
    const at = a.title.toLocaleLowerCase();
    const bt = b.title.toLocaleLowerCase();
    if (at !== bt) return at.localeCompare(bt);
    return a.key.localeCompare(b.key);
  });
  return {
    enabled: !!data.enabled,
    connected: !!data.connected,
    server: data.server || null,
    tokenConfigured: !!data.token_configured,
    libraries: sortedLibraries,
    favoriteKeys,
    favoriteSet,
    lastRefreshes: data.last_refreshes || {},
    query: typeof _plexState.query === "string" ? _plexState.query : "",
    error: String(data.error || ""),
  };
}

function renderPlexSummary() {
  const summary = document.getElementById("plex-page-summary");
  const badge = document.getElementById("plex-page-status-badge");
  const label = document.getElementById("plex-page-status-text");
  const count = document.getElementById("plex-page-count");
  if (!summary || !badge || !label) return;

  const state = _plexState;
  const total = state.libraries.length;
  const favoriteCount = state.favoriteKeys.length;
  if (count) {
    count.textContent = t("plex_page_counts", { favorites: favoriteCount, total });
  }

  if (!state.enabled) {
    badge.className = "conn-badge unknown";
    label.textContent = t("plex_disabled");
    summary.innerHTML = `<p class="form-hint">${escHtml(t("plex_page_disabled"))}</p>`;
    return;
  }

  if (!state.connected) {
    const message = state.error || (state.tokenConfigured ? t("plex_unavailable") : t("plex_not_configured"));
    badge.className = `conn-badge ${state.error ? "error" : "unknown"}`;
    label.textContent = state.error ? t("plex_unavailable") : (state.tokenConfigured ? t("plex_unavailable") : t("plex_not_configured"));
    summary.innerHTML = `
      <p class="form-hint" style="color:var(--red)">${escHtml(message)}</p>`;
    return;
  }

  badge.className = "conn-badge ok";
  label.textContent = t("plex_connected");
  const serverName = state.server && state.server.friendlyName ? state.server.friendlyName : "-";
  summary.innerHTML = `
    <div class="plex-summary-grid">
      <div>
        <strong style="color:var(--text)">${escHtml(serverName)}</strong><br>
        ${escHtml(t("plex_libraries_count", { n: total }))}
      </div>
      <div class="plex-summary-pill">${escHtml(t("plex_page_favorites_count", { n: favoriteCount }))}</div>
    </div>`;
}

function getPlexVisibleLibraries() {
  const query = String(_plexState.query || "").trim().toLocaleLowerCase();
  if (!query) return _plexState.libraries.slice();
  return _plexState.libraries.filter((library) => {
    const haystack = `${library.title} ${library.type} ${library.key}`.toLocaleLowerCase();
    return haystack.includes(query);
  });
}

function buildPlexRow(library, options = {}) {
  const key = library.key;
  const last = formatPlexRefreshTime(_plexState.lastRefreshes[key]);
  const favorite = !!options.favorite;
  const moveUpDisabled = !!options.moveUpDisabled;
  const moveDownDisabled = !!options.moveDownDisabled;
  const starTitle = favorite ? t("plex_favorite_remove") : t("plex_favorite_add");
  const starIcon = favorite ? "★" : "☆";
  return `
    <div class="plex-library-row ${favorite ? "is-favorite" : ""}" data-plex-key="${escHtml(key)}">
      <div class="plex-row-main">
        <button class="plex-star-btn ${favorite ? "active" : ""}" type="button" data-plex-action="toggle-favorite" data-plex-key="${escHtml(key)}" aria-label="${escHtml(starTitle)}" title="${escHtml(starTitle)}">${starIcon}</button>
        <div class="plex-library-info">
          <span class="plex-library-title">${escHtml(library.title || key)}</span>
          <span class="plex-library-meta">${escHtml(library.type || "")} · ${escHtml(t("plex_last_refresh", { time: last }))}</span>
        </div>
      </div>
      <div class="plex-row-actions">
        ${favorite ? `
          <button class="btn btn-sm plex-order-btn" type="button" data-plex-action="move-up" data-plex-key="${escHtml(key)}" ${moveUpDisabled ? "disabled" : ""} aria-label="${escHtml(t('plex_move_up'))}">↑</button>
          <button class="btn btn-sm plex-order-btn" type="button" data-plex-action="move-down" data-plex-key="${escHtml(key)}" ${moveDownDisabled ? "disabled" : ""} aria-label="${escHtml(t('plex_move_down'))}">↓</button>
        ` : ""}
        <button class="btn btn-sm plex-refresh-btn" type="button" data-plex-action="refresh" data-plex-key="${escHtml(key)}">${escHtml(t("plex_btn_refresh_library"))}</button>
      </div>
    </div>`;
}

function renderPlexLists() {
  const list = document.getElementById("plex-page-libraries");
  if (!list) return;

  const visibleLibraries = getPlexVisibleLibraries();
  const visibleKeys = new Set(visibleLibraries.map((library) => library.key));
  const favoriteLibraries = _plexState.favoriteKeys
    .map((key) => _plexState.libraries.find((library) => library.key === key))
    .filter(Boolean)
    .filter((library) => visibleKeys.has(library.key));
  const favoriteSet = new Set(favoriteLibraries.map((library) => library.key));
  const otherLibraries = visibleLibraries.filter((library) => !favoriteSet.has(library.key));

  const sections = [];

  if (favoriteLibraries.length) {
    sections.push(`
      <section class="plex-section">
        <div class="plex-section-header">
          <div>
            <h2 data-i18n="plex_favorites_title">Favorites</h2>
            <p class="form-hint" data-i18n="plex_reorder_hint">Favorites stay at the top and can be reordered manually.</p>
          </div>
          <span class="plex-count-pill">${escHtml(t("plex_page_favorites_count", { n: favoriteLibraries.length }))}</span>
        </div>
        <div class="plex-section-list">
          ${favoriteLibraries.map((library, index) => buildPlexRow(library, {
            favorite: true,
            moveUpDisabled: index === 0,
            moveDownDisabled: index === favoriteLibraries.length - 1,
          })).join("")}
        </div>
      </section>`);
  } else if (String(_plexState.query || "").trim() === "") {
    sections.push(`
      <section class="plex-section">
        <div class="plex-section-header">
          <div>
            <h2 data-i18n="plex_favorites_title">Favorites</h2>
            <p class="form-hint" data-i18n="plex_reorder_hint">Favorites stay at the top and can be reordered manually.</p>
          </div>
        </div>
        <div class="empty-state plex-empty-block">
          <p data-i18n="plex_no_favorites">No favorites yet. Tap the star on a library to pin it here.</p>
        </div>
      </section>`);
  }

  sections.push(`
    <section class="plex-section">
      <div class="plex-section-header">
        <div>
          <h2 data-i18n="plex_all_title">All libraries</h2>
          <p class="form-hint" data-i18n="plex_alpha_hint">The rest stays sorted alphabetically.</p>
        </div>
        <span class="plex-count-pill">${escHtml(t("plex_page_total_count", { n: otherLibraries.length }))}</span>
      </div>
      <div class="plex-section-list">
        ${otherLibraries.length ? otherLibraries.map((library) => buildPlexRow(library)).join("") : `<div class="empty-state plex-empty-block"><p>${escHtml(t("plex_page_empty"))}</p></div>`}
      </div>
    </section>`);

  list.innerHTML = sections.join("");
}

function renderPlexPage(data) {
  _plexState = normalizePlexState(data);
  renderPlexSummary();
  renderPlexLists();
}

async function loadPlexPage() {
  setPlexPageBadge("checking", t("settings_checking"));
  const list = document.getElementById("plex-page-libraries");
  if (list) list.innerHTML = `<p class="form-hint">${escHtml(t("plex_page_loading"))}</p>`;
  try {
    const data = await API.get("/api/settings/plex");
    renderPlexPage(data);
  } catch (e) {
    setPlexPageBadge("error", t("plex_unavailable"));
    const summary = document.getElementById("plex-page-summary");
    if (summary) summary.innerHTML = `<p class="form-hint" style="color:var(--red)">${escHtml(e.message)}</p>`;
    if (list) list.innerHTML = `<p class="form-hint" style="color:var(--red)">${escHtml(e.message)}</p>`;
  }
}

function initPlexPageEvents() {
  const search = document.getElementById("plex-search");
  if (search && !search.dataset.bound) {
    search.dataset.bound = "1";
    search.addEventListener("input", () => {
      _plexState.query = search.value || "";
      renderPlexLists();
    });
  }

  const list = document.getElementById("plex-page-libraries");
  if (list && !list.dataset.bound) {
    list.dataset.bound = "1";
    list.addEventListener("click", handlePlexAction);
  }
}

async function savePlexFavoriteKeys(nextKeys) {
  await API.put("/api/settings/plex", { favorite_keys: nextKeys });
  _plexState.favoriteKeys = nextKeys.slice();
  renderPlexSummary();
  renderPlexLists();
}

function moveFavoriteKey(key, direction) {
  const index = _plexState.favoriteKeys.indexOf(key);
  if (index < 0) return;
  const next = _plexState.favoriteKeys.slice();
  const target = index + direction;
  if (target < 0 || target >= next.length) return;
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

function getButtonLibraryKey(button) {
  return button && button.getAttribute("data-plex-key") ? String(button.getAttribute("data-plex-key")) : "";
}

async function handlePlexAction(event) {
  const button = event.target.closest("[data-plex-action]");
  if (!button) return;
  const action = button.getAttribute("data-plex-action");
  const key = getButtonLibraryKey(button);
  if (!key) return;

  if (action === "refresh") {
    const originalLabel = button.textContent;
    button.disabled = true;
    button.textContent = t("plex_btn_refreshing");
    try {
      await API.post(`/api/settings/plex/libraries/${encodeURIComponent(key)}/refresh`, {});
      showToast(t("plex_refresh_ok"), "ok");
      await loadPlexPage();
    } catch (e) {
      button.disabled = false;
      button.textContent = originalLabel;
      showToast(t("error_prefix") + e.message, "error");
    }
    return;
  }

  if (action === "toggle-favorite") {
    const current = _plexState.favoriteKeys.slice();
    const exists = current.includes(key);
    const next = exists ? current.filter((item) => item !== key) : [key, ...current];
    try {
      button.disabled = true;
      await savePlexFavoriteKeys(next);
      showToast(exists ? t("plex_favorite_removed") : t("plex_favorite_saved"), "ok");
    } catch (e) {
      showToast(t("error_prefix") + e.message, "error");
      await loadPlexPage();
    } finally {
      button.disabled = false;
    }
    return;
  }

  if (action === "move-up" || action === "move-down") {
    const direction = action === "move-up" ? -1 : 1;
    const next = moveFavoriteKey(key, direction);
    if (!next) return;
    try {
      await savePlexFavoriteKeys(next);
    } catch (e) {
      showToast(t("error_prefix") + e.message, "error");
      await loadPlexPage();
    }
  }
}

async function checkPlexAuth() {
  try {
    const status = await fetch("/api/auth/status").then(r => r.json());
    if (!status.admin_exists) {
      window.location.href = "/";
      return false;
    }

    const token = getAuthToken();
    if (!token) { showPlexLogin(); return false; }

    const check = await fetch("/api/settings/plex", {
      headers: { "Authorization": `Bearer ${token}` },
    });
    if (check.status === 401) {
      localStorage.removeItem("dm_token");
      API.token = "";
      showPlexLogin();
      return false;
    }
    return true;
  } catch {
    return true;
  }
}

function showPlexLogin() {
  document.getElementById("login-modal").classList.remove("hidden");
  document.getElementById("login-form").classList.remove("hidden");
  document.getElementById("otp-group").classList.add("hidden");
  document.getElementById("login-otp").value = "";
  document.getElementById("login-error").classList.add("hidden");
}

async function doPlexLogin() {
  const username = document.getElementById("login-username").value;
  const password = document.getElementById("login-password").value;
  const otpCode = document.getElementById("login-otp").value.trim();
  const errEl = document.getElementById("login-error");

  errEl.classList.add("hidden");

  const body = { username, password };
  if (_plexOtpRequired && otpCode) body.otp_code = otpCode;

  try {
    const resp = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      const data = await resp.json();
      errEl.textContent = data.detail || t("settings_login_invalid");
      errEl.classList.remove("hidden");
      if (_plexOtpRequired) {
        document.getElementById("login-otp").value = "";
        document.getElementById("login-otp").focus();
      }
      return;
    }
    const data = await resp.json();

    if (data.otp_required) {
      _plexOtpRequired = true;
      document.getElementById("otp-group").classList.remove("hidden");
      document.getElementById("login-otp").value = "";
      document.getElementById("login-otp").focus();
      return;
    }

    _plexOtpRequired = false;
    localStorage.setItem("dm_token", data.token);
    API.token = data.token;
    document.getElementById("login-modal").classList.add("hidden");
    bootPlexPage();
  } catch {
    errEl.textContent = t("settings_login_server_error");
    errEl.classList.remove("hidden");
  }
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !document.getElementById("login-modal").classList.contains("hidden")) {
    doPlexLogin();
  }
});

async function bootPlexPage() {
  if (typeof initI18n === "function") initI18n();
  if (typeof initAccountButton === "function") initAccountButton();
  initPlexPageEvents();
  const authed = await checkPlexAuth();
  if (!authed) return;
  await loadPlexPage();
}

bootPlexPage();
