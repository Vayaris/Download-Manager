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

function renderPlexPage(data) {
  const summary = document.getElementById("plex-page-summary");
  const list = document.getElementById("plex-page-libraries");
  if (!summary || !list) return;

  if (!data.enabled) {
    setPlexPageBadge("unknown", t("plex_disabled"));
    summary.innerHTML = `<p class="form-hint">${escHtml(t("plex_page_disabled"))}</p>`;
    list.innerHTML = `
      <div class="empty-state">
        <p>${escHtml(t("plex_page_enable_hint"))}</p>
        <a class="btn btn-primary" href="/settings-page">${escHtml(t("plex_open_settings"))}</a>
      </div>`;
    return;
  }

  if (!data.connected) {
    const message = data.token_configured ? t("plex_unavailable") : t("plex_not_configured");
    setPlexPageBadge(data.token_configured ? "error" : "unknown", message);
    summary.innerHTML = `
      <p class="form-hint" style="color:var(--red)">${escHtml(data.error || message)}</p>`;
    list.innerHTML = `
      <div class="empty-state">
        <p>${escHtml(t("plex_page_config_hint"))}</p>
        <a class="btn btn-primary" href="/settings-page">${escHtml(t("plex_open_settings"))}</a>
      </div>`;
    return;
  }

  setPlexPageBadge("ok", t("plex_connected"));
  const serverName = data.server && data.server.friendlyName ? data.server.friendlyName : "-";
  summary.innerHTML = `
    <div style="font-size:13px;color:var(--text-2);line-height:1.6">
      <strong style="color:var(--text)">${escHtml(serverName)}</strong><br>
      ${escHtml(t("plex_libraries_count", { n: data.library_count || 0 }))}
    </div>`;

  const libraries = Array.isArray(data.libraries) ? data.libraries : [];
  if (!libraries.length) {
    list.innerHTML = `<p class="form-hint">${escHtml(t("plex_no_libraries"))}</p>`;
    return;
  }

  const lastRefreshes = data.last_refreshes || {};
  list.innerHTML = libraries.map((library) => {
    const key = String(library.key || "");
    const last = formatPlexRefreshTime(lastRefreshes[key]);
    return `
      <div class="plex-library-row">
        <div>
          <span class="plex-library-title">${escHtml(library.title || key)}</span>
          <span class="plex-library-meta">${escHtml(library.type || "")} · ${escHtml(t("plex_last_refresh", { time: last }))}</span>
        </div>
        <button class="btn btn-sm plex-refresh-btn" type="button" data-plex-refresh-key="${escHtml(key)}">${escHtml(t("plex_btn_refresh_library"))}</button>
      </div>`;
  }).join("");
  bindPlexRefreshButtons();
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
    if (list) list.innerHTML = `<p class="form-hint" style="color:var(--red)">${escHtml(e.message)}</p>`;
  }
}

function bindPlexRefreshButtons() {
  document.querySelectorAll("[data-plex-refresh-key]").forEach((button) => {
    button.addEventListener("click", onPlexRefreshClick);
  });
}

async function onPlexRefreshClick(event) {
  const button = event.currentTarget;
  const key = button.getAttribute("data-plex-refresh-key");
  if (!key) return;

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
  const authed = await checkPlexAuth();
  if (!authed) return;
  await loadPlexPage();
}

bootPlexPage();
