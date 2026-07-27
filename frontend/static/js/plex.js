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
  provider: "plex",
  enabled: false,
  connected: false,
  server: null,
  libraries: [],
  suggestions: [],
  favoriteKeys: [],
  lastRefreshes: {},
  autoRefreshEnabled: false,
  autoRefreshes: {},
  autoRefreshLastResult: null,
  query: "",
  error: "",
};
let _plexDrag = null;

function normalizePlexState(data) {
  data = data || {};
  const libraries = Array.isArray(data.libraries) ? data.libraries.map((library) => ({
    key: String(library.key || "").trim(),
    title: String(library.title || "").trim(),
    type: String(library.type || "").trim(),
    locations: Array.isArray(library.locations) ? library.locations.map((path) => String(path || "").trim()).filter(Boolean) : [],
  })).filter((library) => library.key && library.title) : [];
  const suggestions = Array.isArray(data.suggestions) ? data.suggestions.map((item) => ({
    historyId: String(item.history_id || "").trim(),
    libraryKey: String(item.library_key || "").trim(),
    libraryTitle: String(item.library_title || "").trim(),
    libraryType: String(item.library_type || "").trim(),
    downloadName: String(item.download_name || "").trim(),
    destination: String(item.destination || "").trim(),
    completedAt: String(item.completed_at || "").trim(),
    matchedLocation: String(item.matched_location || "").trim(),
    matchedCandidate: String(item.matched_candidate || "").trim(),
    mappedFrom: String(item.mapped_from || "").trim(),
  })).filter((item) => item.historyId && item.libraryKey && item.libraryTitle) : [];
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
    provider: data.provider || "plex",
    enabled: !!data.enabled,
    connected: !!data.connected,
    server: data.server || null,
    tokenConfigured: !!data.token_configured,
    libraries: sortedLibraries,
    suggestions,
    favoriteKeys,
    favoriteSet,
    lastRefreshes: data.last_refreshes || {},
    autoRefreshEnabled: !!data.auto_refresh_enabled,
    autoRefreshes: data.auto_refreshes || {},
    autoRefreshLastResult: data.auto_refresh_last_result || null,
    query: typeof _plexState.query === "string" ? _plexState.query : "",
    error: String(data.error || ""),
  };
}

function formatPlexCompletedTime(value) {
  if (!value) return "";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function renderPlexSummary() {
  const badge = document.getElementById("plex-page-status-badge");
  const label = document.getElementById("plex-page-status-text");
  const count = document.getElementById("plex-page-count");
  const serverMeta = document.getElementById("plex-server-meta");
  if (!badge || !label) return;

  const state = _plexState;
  const total = state.libraries.length;
  const providerName = state.provider === "jellyfin" ? "Jellyfin" : "Plex";
  document.querySelectorAll("[data-media-provider-label], [data-media-nav-label]").forEach((el) => { el.textContent = providerName; });
  const title = document.querySelector("[data-media-page-title]");
  if (title) title.textContent = t("media_page_title", { provider: providerName });
  const subtitle = document.querySelector("[data-media-page-subtitle]");
  if (subtitle) subtitle.textContent = t("media_page_subtitle", { provider: providerName });
  document.querySelectorAll("[data-media-settings-link]").forEach((el) => {
    el.textContent = t("media_open_settings", { provider: providerName });
  });
  if (count) {
    count.textContent = t("plex_libraries_count", { n: total });
  }
  if (serverMeta) serverMeta.textContent = "";

  if (!state.enabled) {
    badge.className = "conn-badge unknown";
    label.textContent = t("plex_disabled");
    if (serverMeta) serverMeta.textContent = t("media_page_disabled", { provider: providerName });
    return;
  }

  if (!state.connected) {
    const message = state.error || (state.tokenConfigured ? t("plex_unavailable") : t("plex_not_configured"));
    badge.className = `conn-badge ${state.error ? "error" : "unknown"}`;
    label.textContent = state.error ? t("plex_unavailable") : (state.tokenConfigured ? t("plex_unavailable") : t("plex_not_configured"));
    if (serverMeta) serverMeta.textContent = message;
    return;
  }

  badge.className = "conn-badge ok";
  label.textContent = t("plex_connected");
  const serverName = state.server && state.server.friendlyName ? state.server.friendlyName : "-";
  if (serverMeta) {
    serverMeta.textContent = `${serverName} · ${t("plex_libraries_count", { n: total })}`;
  }
}

function buildPlexSuggestionRow(item) {
  const completed = formatPlexCompletedTime(item.completedAt);
  return `
    <div class="plex-suggestion-row">
      <div class="plex-suggestion-main">
        <span class="plex-suggestion-label">${escHtml(t("plex_suggestion_library", { library: item.libraryTitle }))}</span>
        <span class="plex-library-meta">${escHtml(item.downloadName || t("plex_suggestion_unknown_download"))}${completed ? ` · ${escHtml(completed)}` : ""}</span>
        ${item.mappedFrom ? `<span class="plex-suggestion-path">${escHtml(t("jellyfin_suggestion_mapping", { source: item.destination, target: item.matchedCandidate || item.matchedLocation }))}</span>` : item.matchedLocation ? `<span class="plex-suggestion-path">${escHtml(t("plex_suggestion_path", { path: item.matchedLocation }))}</span>` : ""}
      </div>
      <button class="btn btn-sm plex-refresh-btn" type="button" data-plex-action="refresh" data-plex-key="${escHtml(item.libraryKey)}">${escHtml(t("plex_btn_refresh_library"))}</button>
    </div>`;
}

function getLatestAutoRefresh() {
  const entries = Object.values(_plexState.autoRefreshes || {})
    .filter((item) => item && item.refreshed_at)
    .sort((a, b) => String(b.refreshed_at).localeCompare(String(a.refreshed_at)));
  return entries[0] || null;
}

function buildPlexAutoRefreshBanner() {
  if (!_plexState.autoRefreshEnabled || String(_plexState.query || "").trim() !== "") return "";
  const latest = getLatestAutoRefresh();
  const result = _plexState.autoRefreshLastResult;
  const providerName = _plexState.provider === "jellyfin" ? "Jellyfin" : "Plex";
  const unmatched = result && Array.isArray(result.unmatched_destinations) ? result.unmatched_destinations.filter(Boolean) : [];
  if (_plexState.provider === "jellyfin" && result && (result.status === "unmatched" || result.status === "partial") && unmatched.length) {
    return `
      <section class="plex-section plex-auto-refresh-section is-warning">
        <div class="plex-auto-refresh-icon">!</div>
        <div>
          <h2>${escHtml(t("media_auto_refresh_unmatched_title"))}</h2>
          <p class="form-hint">${escHtml(t("media_auto_refresh_unmatched_hint"))}</p>
          <div class="media-unmatched-paths">${unmatched.map((path) => `<code>${escHtml(path)}</code>`).join("")}</div>
          <a class="btn btn-sm" href="/settings-page#media-settings">${escHtml(t("media_auto_refresh_configure_mapping"))}</a>
        </div>
      </section>`;
  }
  const detail = latest
    ? t("media_auto_refresh_last", {
        library: latest.library_title || latest.library_key || "-",
        time: formatPlexRefreshTime(latest.refreshed_at),
      })
    : t("media_auto_refresh_waiting");
  return `
    <section class="plex-section plex-auto-refresh-section">
      <div class="plex-auto-refresh-icon">A</div>
      <div>
        <h2>${escHtml(t("media_auto_refresh_banner_title", { provider: providerName }))}</h2>
        <p class="form-hint">${escHtml(detail)}</p>
      </div>
    </section>`;
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
  const starTitle = favorite ? t("plex_favorite_remove") : t("plex_favorite_add");
  const starIcon = favorite ? "★" : "☆";
  const jellyfinPaths = _plexState.provider === "jellyfin" && library.locations.length
    ? `<span class="plex-suggestion-path">${escHtml(t("jellyfin_library_paths", { paths: library.locations.join(" · ") }))}</span>`
    : "";
  return `
    <div class="plex-library-row ${favorite ? "is-favorite" : ""}" data-plex-key="${escHtml(key)}">
      <div class="plex-row-main">
        ${favorite ? `<button class="plex-drag-handle" type="button" data-plex-drag-key="${escHtml(key)}" aria-label="${escHtml(t("plex_drag_handle"))}" title="${escHtml(t("plex_drag_handle"))}">☰</button>` : ""}
        <button class="plex-star-btn ${favorite ? "active" : ""}" type="button" data-plex-action="toggle-favorite" data-plex-key="${escHtml(key)}" aria-label="${escHtml(starTitle)}" title="${escHtml(starTitle)}">${starIcon}</button>
        <div class="plex-library-info">
          <span class="plex-library-title">${escHtml(library.title || key)}</span>
          <span class="plex-library-meta">${escHtml(library.type || "")} · ${escHtml(t("plex_last_refresh", { time: last }))}</span>
          ${jellyfinPaths}
        </div>
      </div>
      <div class="plex-row-actions">
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
  const autoRefreshBanner = buildPlexAutoRefreshBanner();
  if (autoRefreshBanner) sections.push(autoRefreshBanner);

  if (_plexState.connected && _plexState.suggestions.length && String(_plexState.query || "").trim() === "") {
    sections.push(`
      <section class="plex-section plex-suggestions-section">
        <div class="plex-section-header">
          <div>
            <h2>${escHtml(t("plex_suggestions_title"))}</h2>
            <p class="form-hint plex-subtle-hint">${escHtml(t("plex_suggestions_hint"))}</p>
          </div>
          <span class="plex-count-pill">${escHtml(t("plex_suggestions_count", { n: _plexState.suggestions.length }))}</span>
        </div>
        <div class="plex-suggestions-list">
          ${_plexState.suggestions.map(buildPlexSuggestionRow).join("")}
        </div>
      </section>`);
  }

  if (favoriteLibraries.length) {
    sections.push(`
      <section class="plex-section">
        <div class="plex-section-header">
          <div>
            <h2>${escHtml(t("plex_favorites_title"))}</h2>
          </div>
          <span class="plex-count-pill">${escHtml(t("plex_page_favorites_count", { n: favoriteLibraries.length }))}</span>
        </div>
        <div class="plex-section-list" data-plex-favorites-list="1">
          ${favoriteLibraries.map((library, index) => buildPlexRow(library, {
            favorite: true,
          })).join("")}
        </div>
      </section>`);
  } else if (String(_plexState.query || "").trim() === "") {
    sections.push(`
      <section class="plex-section">
        <div class="plex-section-header">
          <div>
            <h2>${escHtml(t("plex_favorites_title"))}</h2>
          </div>
        </div>
        <div class="empty-state plex-empty-block">
          <p>${escHtml(t("plex_no_favorites"))}</p>
        </div>
      </section>`);
  }

  sections.push(`
    <section class="plex-section">
      <div class="plex-section-header">
        <div>
          <h2>${escHtml(t("plex_all_title"))}</h2>
          <p class="form-hint plex-subtle-hint">${escHtml(t("plex_alpha_hint"))}</p>
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
    const data = await API.get("/api/settings/media");
    if (data && data.enabled && data.connected) {
      try {
        const suggestions = await API.get("/api/settings/media/suggestions");
        data.suggestions = Array.isArray(suggestions.suggestions) ? suggestions.suggestions : [];
      } catch {
        data.suggestions = [];
      }
    }
    renderPlexPage(data);
  } catch (e) {
    setPlexPageBadge("error", t("plex_unavailable"));
    const serverMeta = document.getElementById("plex-server-meta");
    if (serverMeta) serverMeta.textContent = e.message;
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
    list.addEventListener("pointerdown", startPlexFavoriteDrag);
  }
}

async function savePlexFavoriteKeys(nextKeys) {
  await API.put("/api/settings/media", { provider: _plexState.provider, favorite_keys: nextKeys });
  _plexState.favoriteKeys = nextKeys.slice();
  renderPlexSummary();
  renderPlexLists();
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
      await API.post(`/api/settings/media/libraries/${encodeURIComponent(key)}/refresh`, {});
      showToast(t(_plexState.provider === "jellyfin" ? "jellyfin_refresh_ok" : "plex_refresh_ok"), "ok");
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

}

function startPlexFavoriteDrag(event) {
  const handle = event.target.closest("[data-plex-drag-key]");
  if (!handle || _plexDrag) return;

  const row = handle.closest(".plex-library-row");
  const list = row && row.closest("[data-plex-favorites-list]");
  const key = handle.getAttribute("data-plex-drag-key");
  if (!row || !list || !key) return;

  event.preventDefault();
  handle.setPointerCapture?.(event.pointerId);
  _plexDrag = {
    key,
    row,
    list,
    handle,
    pointerId: event.pointerId,
    originalKeys: getPlexFavoriteKeysFromDom(list),
  };
  row.classList.add("is-dragging");
  list.classList.add("is-sorting");
  document.body.classList.add("plex-drag-active");
  window.addEventListener("pointermove", movePlexFavoriteDrag);
  window.addEventListener("pointerup", endPlexFavoriteDrag);
  window.addEventListener("pointercancel", cancelPlexFavoriteDrag);
}

function movePlexFavoriteDrag(event) {
  if (!_plexDrag || event.pointerId !== _plexDrag.pointerId) return;
  event.preventDefault();

  const after = getPlexDragAfterRow(_plexDrag.list, event.clientY, _plexDrag.row);
  if (after) {
    _plexDrag.list.insertBefore(_plexDrag.row, after);
  } else {
    _plexDrag.list.appendChild(_plexDrag.row);
  }
}

function getPlexDragAfterRow(list, y, draggedRow) {
  const rows = [...list.querySelectorAll(".plex-library-row:not(.is-dragging)")].filter((row) => row !== draggedRow);
  return rows.reduce((closest, row) => {
    const box = row.getBoundingClientRect();
    const offset = y - box.top - box.height / 2;
    if (offset < 0 && offset > closest.offset) {
      return { offset, row };
    }
    return closest;
  }, { offset: Number.NEGATIVE_INFINITY, row: null }).row;
}

function getPlexFavoriteKeysFromDom(list) {
  return [...list.querySelectorAll(".plex-library-row")]
    .map((row) => row.getAttribute("data-plex-key"))
    .filter(Boolean);
}

function finishPlexFavoriteDrag() {
  if (!_plexDrag) return null;
  const drag = _plexDrag;
  drag.row.classList.remove("is-dragging");
  drag.list.classList.remove("is-sorting");
  try { drag.handle.releasePointerCapture?.(drag.pointerId); } catch {}
  document.body.classList.remove("plex-drag-active");
  window.removeEventListener("pointermove", movePlexFavoriteDrag);
  window.removeEventListener("pointerup", endPlexFavoriteDrag);
  window.removeEventListener("pointercancel", cancelPlexFavoriteDrag);
  _plexDrag = null;
  return drag;
}

async function endPlexFavoriteDrag(event) {
  if (!_plexDrag || event.pointerId !== _plexDrag.pointerId) return;
  const drag = finishPlexFavoriteDrag();
  const nextKeys = getPlexFavoriteKeysFromDom(drag.list);
  if (nextKeys.join("|") === drag.originalKeys.join("|")) return;

  try {
    await savePlexFavoriteKeys(nextKeys);
    showToast(t("plex_reorder_saved"), "ok");
  } catch (e) {
    showToast(t("error_prefix") + e.message, "error");
    await loadPlexPage();
  }
}

async function cancelPlexFavoriteDrag(event) {
  if (!_plexDrag || event.pointerId !== _plexDrag.pointerId) return;
  const drag = finishPlexFavoriteDrag();
  try {
    await savePlexFavoriteKeys(drag.originalKeys);
  } catch {
    await loadPlexPage();
  }
}

async function checkPlexAuth() {
  try {
    const status = await fetch("/api/auth/status").then(r => r.json());
    if (!status.admin_exists) {
      window.location.href = "/";
      return false;
    }

    const check = await fetch("/api/settings/media", { credentials: "same-origin" });
    if (check.status === 401) {
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
    localStorage.removeItem("dm_token");
    API.token = "";
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
