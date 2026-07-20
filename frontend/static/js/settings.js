// ============================================================
//  Settings page v2
// ============================================================

// Values now read directly from input fields

// API helper — delegates to shared apiFetch from api.js
const API = apiFetch;

// ---- AllDebrid connection badge ----

function setAllDebridBadge(state, text) {
  const badge = document.getElementById("alldebrid-status-badge");
  const label = document.getElementById("alldebrid-status-text");
  badge.className = `conn-badge ${state}`;
  label.textContent = text;
}

async function testAllDebrid() {
  const key = document.getElementById("alldebrid-key").value.trim();
  if (key) {
    try { await API.put("/api/settings/", { alldebrid_api_key: key }); } catch {}
  }
  setAllDebridBadge("checking", t("settings_checking"));
  try {
    const res = await API.post("/api/settings/test-alldebrid", {});
    if (res.valid) {
      setAllDebridBadge("ok", t("settings_connected"));
      showToast(t("settings_key_valid"), "ok");
      // Auto-enable when key is valid
      document.getElementById("alldebrid-enabled").checked = true;
      await API.put("/api/settings/", { alldebrid_enabled: true });
      window._alldebridKeyConfigured = true;
      await refreshAllDebridHosts();
    } else {
      setAllDebridBadge("error", t("settings_invalid_key"));
      showToast(t("settings_key_invalid"), "error");
    }
  } catch (e) {
    setAllDebridBadge("error", t("settings_error"));
    showToast(t("error_prefix") + e.message, "error");
  }
}

async function checkAllDebridStatus() {
  const key = document.getElementById("alldebrid-key").value.trim();
  if (!key && !window._alldebridKeyConfigured) {
    setAllDebridBadge("unknown", t("settings_not_configured"));
    return;
  }
  setAllDebridBadge("checking", t("settings_checking"));
  try {
    const res = await API.post("/api/settings/test-alldebrid", {});
    setAllDebridBadge(res.valid ? "ok" : "error", res.valid ? t("settings_connected") : t("settings_invalid_key"));
  } catch {
    setAllDebridBadge("error", t("settings_connection_error"));
  }
}

async function saveAllDebrid() {
  const key = document.getElementById("alldebrid-key").value.trim();
  const enabled = document.getElementById("alldebrid-enabled").checked;
  const payload = { alldebrid_enabled: enabled };
  if (key) payload.alldebrid_api_key = key;
  try {
    await API.put("/api/settings/", payload);
    showToast(t("settings_alldebrid_saved"), "ok");
    if (key) {
      window._alldebridKeyConfigured = true;
      document.getElementById("alldebrid-key").value = "";
    }
    await checkAllDebridStatus();
    await refreshAllDebridHosts();
  } catch (e) {
    showToast(t("error_prefix") + e.message, "error");
  }
}

// ---- YouTube direct mode ----

function setYouTubeStatus(state, text) {
  const badge = document.getElementById("youtube-status-badge");
  const label = document.getElementById("youtube-status-text");
  if (!badge || !label) return;
  badge.className = `conn-badge ${state}`;
  label.textContent = text;
}

function renderYouTubeStatus(status) {
  const panel = document.getElementById("youtube-dependencies");
  const install = document.getElementById("youtube-install-btn");
  if (!panel || !install) return;
  const dependencies = [
    `yt-dlp: ${status.yt_dlp?.available ? status.yt_dlp.version : t("settings_youtube_missing")}`,
    `ffmpeg: ${status.ffmpeg?.available ? t("settings_youtube_available") : t("settings_youtube_missing")}`,
    `Deno: ${status.deno?.available ? t("settings_youtube_available") : t("settings_youtube_missing")}`,
  ];
  panel.textContent = status.installing
    ? t("settings_youtube_installing")
    : (status.error ? `${t("settings_error")}: ${status.error}` : dependencies.join(" · "));
  panel.dataset.state = status.ready ? "ok" : (status.error ? "error" : "warning");
  install.disabled = !!status.installing;
  install.classList.toggle("hidden", !!status.ready);
  setYouTubeStatus(
    status.ready ? "ok" : (status.installing ? "checking" : "unknown"),
    status.ready ? t("settings_youtube_ready") : (status.installing ? t("settings_youtube_installing_short") : t("settings_youtube_optional")),
  );

  const cookiePanel = document.getElementById("youtube-cookies-status");
  const deleteButton = document.getElementById("youtube-cookies-delete");
  const configured = status.cookies?.configured === true;
  if (cookiePanel) {
    let updated = "";
    if (configured && status.cookies.updated_at) {
      const date = new Date(status.cookies.updated_at);
      if (!Number.isNaN(date.getTime())) updated = date.toLocaleString(getLang());
    }
    cookiePanel.dataset.state = configured ? "ok" : "warning";
    cookiePanel.textContent = configured
      ? t("settings_youtube_cookies_configured", {
          count: status.cookies.count || 0,
          date: updated || t("settings_youtube_cookies_date_unknown"),
        })
      : t("settings_youtube_cookies_missing");
  }
  if (deleteButton) deleteButton.classList.toggle("hidden", !configured);
}

async function loadYouTubeStatus() {
  try {
    const status = await API.get("/api/settings/youtube/status");
    renderYouTubeStatus(status);
    return status;
  } catch (error) {
    setYouTubeStatus("error", t("settings_error"));
    const panel = document.getElementById("youtube-dependencies");
    if (panel) {
      panel.dataset.state = "error";
      panel.textContent = `${t("settings_error")}: ${error.message}`;
    }
    return null;
  }
}

async function installYouTubeDependencies() {
  if (!confirm(t("settings_youtube_install_confirm"))) return;
  try {
    let status = await API.post("/api/settings/youtube/install", {});
    renderYouTubeStatus(status);
    while (status.installing) {
      await new Promise((resolve) => setTimeout(resolve, 2000));
      status = await API.get("/api/settings/youtube/status");
      renderYouTubeStatus(status);
    }
    showToast(status.ready ? t("settings_youtube_install_ok") : `${t("settings_error")}: ${status.error || t("settings_youtube_install_failed")}`, status.ready ? "ok" : "error");
  } catch (error) {
    showToast(t("error_prefix") + error.message, "error");
    await loadYouTubeStatus();
  }
}

async function uploadYouTubeCookies() {
  const input = document.getElementById("youtube-cookies-file");
  const file = input?.files?.[0];
  if (!file) {
    showToast(t("settings_youtube_cookies_choose"), "error");
    return;
  }
  const form = new FormData();
  form.append("file", file, file.name);
  try {
    const response = await fetch("/api/settings/youtube/cookies", {
      method: "POST",
      credentials: "same-origin",
      body: form,
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.detail || t("settings_youtube_cookies_import_failed"));
    input.value = "";
    await loadYouTubeStatus();
    showToast(t("settings_youtube_cookies_imported"), "ok");
  } catch (error) {
    showToast(t("error_prefix") + error.message, "error");
  }
}

async function deleteYouTubeCookies() {
  if (!confirm(t("settings_youtube_cookies_delete_confirm"))) return;
  try {
    await API.del("/api/settings/youtube/cookies");
    const input = document.getElementById("youtube-cookies-file");
    if (input) input.value = "";
    await loadYouTubeStatus();
    showToast(t("settings_youtube_cookies_deleted"), "ok");
  } catch (error) {
    showToast(t("error_prefix") + error.message, "error");
  }
}

async function saveYouTubeSettings() {
  const concurrent = Math.min(4, Math.max(1, parseInt(document.getElementById("youtube-concurrency").value) || 2));
  const speed = Math.max(0, parseInt(document.getElementById("youtube-speed-limit").value) || 0);
  document.getElementById("youtube-concurrency").value = concurrent;
  document.getElementById("youtube-speed-limit").value = speed;
  try {
    await API.put("/api/settings/", {
      youtube_direct_enabled: document.getElementById("youtube-direct-enabled").checked,
      youtube_max_concurrent: concurrent,
      youtube_speed_limit: speed,
    });
    showToast(t("settings_youtube_saved"), "ok");
  } catch (error) {
    showToast(t("error_prefix") + error.message, "error");
  }
}

// ---- Other settings ----

async function saveDownloadSettings() {
  const simultaneous = Math.min(20, Math.max(1, parseInt(document.getElementById("simultaneous-input").value) || 3));
  const segments = Math.min(16, Math.max(1, parseInt(document.getElementById("segments-input").value) || 1));
  const speedLimit = parseInt(document.getElementById("speed-limit").value) || 0;
  const maxRetriesRaw = parseInt(document.getElementById("max-retries-input").value);
  const retryDelayRaw = parseInt(document.getElementById("retry-delay-input").value);
  const stalledTimeoutRaw = parseInt(document.getElementById("stalled-timeout-input").value);
  const maxRetries = Math.min(20, Math.max(0, Number.isNaN(maxRetriesRaw) ? 3 : maxRetriesRaw));
  const retryDelay = Math.min(3600, Math.max(0, Number.isNaN(retryDelayRaw) ? 5 : retryDelayRaw));
  const stalledTimeout = Math.min(168, Math.max(0, Number.isNaN(stalledTimeoutRaw) ? 3 : stalledTimeoutRaw));
  const skipNfo = document.getElementById("skip-nfo-files").checked;
  const dest = document.getElementById("default-dest").value.trim() || undefined;

  // Clamp input values visually
  document.getElementById("simultaneous-input").value = simultaneous;
  document.getElementById("segments-input").value = segments;
  document.getElementById("max-retries-input").value = maxRetries;
  document.getElementById("retry-delay-input").value = retryDelay;
  document.getElementById("stalled-timeout-input").value = stalledTimeout;

  try {
    const result = await API.put("/api/settings/", {
      simultaneous_downloads: simultaneous,
      download_segments: segments,
      speed_limit: speedLimit,
      max_retries: maxRetries,
      retry_delay_seconds: retryDelay,
      stalled_timeout_hours: stalledTimeout,
      skip_nfo_files: skipNfo,
      default_destination: dest,
    });
    if (result.speed_limit) renderSpeedLimitStatus(result.speed_limit);
    showToast(t("settings_downloads_saved"), "ok");
  } catch (e) {
    showToast(t("error_prefix") + e.message, "error");
  }
}

let allDebridHosts = [];

function renderAllDebridHosts() {
  const list = document.getElementById("alldebrid-hosts-list");
  const summary = document.getElementById("alldebrid-hosts-summary");
  const searchEl = document.getElementById("alldebrid-hosts-search");
  if (!list || !summary || !searchEl) return;

  const query = searchEl.value.trim().toLowerCase();
  const filtered = allDebridHosts.filter((host) => {
    const haystack = [host.name, host.type, ...(host.domains || [])].join(" ").toLowerCase();
    return !query || haystack.includes(query);
  });
  const available = allDebridHosts.filter((host) => host.status).length;

  summary.textContent = t("settings_hosts_summary", {
    available,
    total: allDebridHosts.length,
    shown: filtered.length,
  });

  if (!filtered.length) {
    list.innerHTML = `<p class="form-hint">${t("settings_hosts_empty")}</p>`;
    return;
  }

  list.innerHTML = filtered.map((host) => {
    const domains = (host.domains || []).slice(0, 3).join(", ");
    const title = domains ? `${host.name} - ${domains}` : host.name;
    const type = host.type ? `<span class="host-chip-type">${escHtml(host.type)}</span>` : "";
    return `<span class="host-chip ${host.status ? "" : "disabled"}" title="${escHtml(title)}">${escHtml(host.name)}${type}</span>`;
  }).join("");
}

async function refreshAllDebridHosts() {
  const panel = document.getElementById("alldebrid-hosts-panel");
  const list = document.getElementById("alldebrid-hosts-list");
  const summary = document.getElementById("alldebrid-hosts-summary");
  if (!panel || !list || !summary) return;

  if (!window._alldebridKeyConfigured || !document.getElementById("alldebrid-enabled").checked) {
    panel.classList.add("hidden");
    allDebridHosts = [];
    return;
  }

  panel.classList.remove("hidden");
  summary.textContent = t("settings_hosts_loading");
  list.innerHTML = "";

  try {
    const res = await API.get("/api/settings/alldebrid/hosts");
    allDebridHosts = Array.isArray(res.hosts) ? res.hosts : [];
    renderAllDebridHosts();
  } catch (e) {
    allDebridHosts = [];
    summary.textContent = t("settings_hosts_unavailable");
    list.innerHTML = `<p class="form-hint" style="color:var(--red)">${escHtml(e.message)}</p>`;
  }
}

function toggleMediaProviderFields() {
  const provider = document.getElementById("media-provider")?.value || "plex";
  document.getElementById("plex-fields")?.classList.toggle("hidden", provider !== "plex");
  document.getElementById("jellyfin-fields")?.classList.toggle("hidden", provider !== "jellyfin");
  document.querySelectorAll("[data-media-nav-label]").forEach((el) => {
    el.textContent = provider === "jellyfin" ? "Jellyfin" : "Plex";
  });
}

function renderMediaSettings(data) {
  const provider = document.getElementById("media-provider");
  const enabled = document.getElementById("media-enabled");
  const autoRefreshEnabled = document.getElementById("media-auto-refresh-enabled");
  const url = document.getElementById("plex-url");
  const token = document.getElementById("plex-token");
  const jellyfinUrl = document.getElementById("jellyfin-url");
  const jellyfinToken = document.getElementById("jellyfin-token");
  if (!provider || !enabled || !autoRefreshEnabled || !url || !token || !jellyfinUrl || !jellyfinToken) return;

  const active = data.provider || "plex";
  const providers = data.providers || {};
  const plexData = providers.plex || (active === "plex" ? data : {});
  const jellyfinData = providers.jellyfin || (active === "jellyfin" ? data : {});

  provider.value = active;
  enabled.checked = !!data.enabled;
  autoRefreshEnabled.checked = !!data.auto_refresh_enabled;
  url.value = plexData.url || "http://127.0.0.1:32400";
  token.value = "";
  token.placeholder = plexData.token_configured ? t("plex_token_configured") : t("plex_token_placeholder");
  jellyfinUrl.value = jellyfinData.url || "http://127.0.0.1:8096";
  jellyfinToken.value = "";
  jellyfinToken.placeholder = jellyfinData.token_configured ? t("jellyfin_token_configured") : t("jellyfin_token_placeholder");
  toggleMediaProviderFields();
}

async function loadMediaSettings() {
  try {
    const data = await API.get("/api/settings/media");
    renderMediaSettings(data);
  } catch (e) {
    showToast(t("error_prefix") + e.message, "error");
  }
}

async function saveMedia() {
  const provider = document.getElementById("media-provider").value || "plex";
  const enabled = document.getElementById("media-enabled").checked;
  const autoRefreshEnabled = document.getElementById("media-auto-refresh-enabled").checked;
  const isJellyfin = provider === "jellyfin";
  const url = (isJellyfin
    ? document.getElementById("jellyfin-url").value.trim()
    : document.getElementById("plex-url").value.trim()) || (isJellyfin ? "http://127.0.0.1:8096" : "http://127.0.0.1:32400");
  const token = (isJellyfin
    ? document.getElementById("jellyfin-token").value.trim()
    : document.getElementById("plex-token").value.trim());
  const payload = { provider, enabled, url, auto_refresh_enabled: autoRefreshEnabled };
  if (token) payload.token = token;
  try {
    await API.put("/api/settings/media", payload);
    document.getElementById("plex-token").value = "";
    document.getElementById("jellyfin-token").value = "";
    showToast(t("media_saved"), "ok");
    await loadMediaSettings();
  } catch (e) {
    showToast(t("error_prefix") + e.message, "error");
    throw e;
  }
}

async function testMedia() {
  try {
    await saveMedia();
    const res = await API.post("/api/settings/media/test", {});
    const key = res.provider === "jellyfin" ? "jellyfin_test_ok" : "plex_test_ok";
    showToast(t(key, { n: res.library_count || 0 }), "ok");
  } catch (e) {
    showToast(t("error_prefix") + e.message, "error");
  }
}

const renderPlexSettings = renderMediaSettings;
const loadPlexSettings = loadMediaSettings;
const savePlex = saveMedia;
const testPlex = testMedia;

function toggleKeyVisibility() {
  const input = document.getElementById("alldebrid-key");
  input.type = input.type === "password" ? "text" : "password";
}

function toggleWebhookFields() {
  const enabled = document.getElementById("webhook-enabled").checked;
  document.getElementById("webhook-fields").classList.toggle("hidden", !enabled);
  const badge = document.getElementById("webhook-state-badge");
  if (badge) {
    badge.classList.toggle("on", enabled);
    badge.classList.toggle("off", !enabled);
    badge.textContent = t(enabled ? "settings_webhook_enabled_state" : "settings_webhook_disabled");
  }
  if (enabled) updateWebhookPreset();
}

async function setWebhookEnabled(enabled) {
  const input = document.getElementById("webhook-enabled");
  input.disabled = true;
  toggleWebhookFields();
  try {
    await API.put("/api/settings/", { webhook_enabled: enabled });
    showToast(t(enabled ? "settings_webhook_enabled_saved" : "settings_webhook_disabled_saved"), "ok");
  } catch (error) {
    input.checked = !enabled;
    toggleWebhookFields();
    showToast(t("error_prefix") + error.message, "error");
  } finally {
    input.disabled = false;
  }
}

function renderSpeedLimitStatus(status) {
  const element = document.getElementById("speed-limit-status");
  if (!element || !status) return;
  if (status.applied) {
    element.dataset.state = "ok";
    element.textContent = status.configured_mb_s > 0
      ? t("settings_speed_applied", { n: status.configured_mb_s })
      : t("settings_speed_unlimited_applied");
    return;
  }
  element.dataset.state = "warning";
  if (status.effective_bytes_s != null) {
    const effective = (status.effective_bytes_s / 1024 / 1024).toFixed(1);
    element.textContent = t("settings_speed_mismatch", { n: effective });
  } else {
    element.textContent = t("settings_speed_pending_restart");
  }
}

async function loadSpeedLimitStatus() {
  try {
    renderSpeedLimitStatus(await API.get("/api/settings/speed-limit/status"));
  } catch {
    renderSpeedLimitStatus({ applied: false, effective_bytes_s: null });
  }
}

const WEBHOOK_PRESETS = {
  generic: {
    placeholder: "https://example.com/webhook",
    badge: null,
    info: null,
  },
  discord: {
    placeholder: "https://discord.com/api/webhooks/...",
    badgeKey: "webhook_badge_free",
    infoKey: "webhook_discord_info",
  },
  slack: {
    placeholder: "https://hooks.slack.com/services/T.../B.../...",
    badgeKey: "webhook_badge_free",
    infoKey: "webhook_slack_info",
  },
  telegram: {
    placeholder: "https://api.telegram.org/bot<TOKEN>/sendMessage",
    badgeKey: "webhook_badge_free",
    infoKey: "webhook_telegram_info",
  },
  gotify: {
    placeholder: "https://gotify.example.com/message?token=...",
    badgeKey: "webhook_badge_free_self",
    infoKey: "webhook_gotify_info",
  },
  ntfy: {
    placeholder: "https://ntfy.sh/your-topic",
    badgeKey: "webhook_badge_free",
    infoKey: "webhook_ntfy_info",
  },
  signal: {
    placeholder: "http://signal-api:8080/v2/send?from=%2B33xxxxxxxxx&to=%2B33xxxxxxxxx",
    badgeKey: "webhook_badge_free_self",
    infoKey: "webhook_signal_info",
  },
};

function updateWebhookPreset() {
  const format = document.getElementById("webhook-format").value;
  const preset = WEBHOOK_PRESETS[format];
  const urlInput = document.getElementById("webhook-url");
  const infoDiv = document.getElementById("webhook-preset-info");
  const urlGroup = document.getElementById("webhook-url-group");
  const signalConfig = document.getElementById("signal-config");

  if (format === "signal") {
    urlGroup.classList.add("hidden");
    signalConfig.classList.remove("hidden");
    // Parse existing URL to prefill fields (if already configured)
    const existing = urlInput.value;
    if (existing && existing.includes("/v2/send")) {
      try {
        const u = new URL(existing);
        document.getElementById("signal-host").value = u.hostname || "localhost";
        document.getElementById("signal-port").value = u.port || "8080";
        document.getElementById("signal-from").value = decodeURIComponent(u.searchParams.get("from") || "");
        document.getElementById("signal-to").value = decodeURIComponent(u.searchParams.get("to") || "");
      } catch {}
    } else {
      if (!document.getElementById("signal-host").value)
        document.getElementById("signal-host").value = "localhost";
      if (!document.getElementById("signal-port").value)
        document.getElementById("signal-port").value = "8080";
    }
    signalBuildUrl();
    infoDiv.classList.add("hidden");
    return;
  }

  urlGroup.classList.remove("hidden");
  signalConfig.classList.add("hidden");

  if (preset && preset.placeholder) {
    urlInput.placeholder = preset.placeholder;
  }

  if (!preset || !preset.infoKey) {
    infoDiv.classList.add("hidden");
    return;
  }

  infoDiv.classList.remove("hidden");
  infoDiv.innerHTML = `
    <div class="preset-header">
      ${preset.badgeKey ? `<span class="preset-badge">${t(preset.badgeKey)}</span>` : ""}
    </div>
    <div class="preset-guide">${t(preset.infoKey)}</div>`;
}

// ---- Signal helpers ----

function signalBuildUrl() {
  const host = document.getElementById("signal-host").value.trim() || "localhost";
  const port = document.getElementById("signal-port").value.trim() || "8080";
  const from = document.getElementById("signal-from").value.trim();
  const to   = document.getElementById("signal-to").value.trim();
  const url  = `http://${host}:${port}/v2/send?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`;
  document.getElementById("webhook-url").value = url;

  // Update registration guide commands
  const fromNum = from || "+33...";
  const el1 = document.getElementById("signal-cmd-about");
  if (el1) el1.textContent = `curl http://${host}:${port}/v1/about`;
  // Update register commands with live captcha/sms fields
  signalUpdateRegisterCmds();

  // Show/hide deploy button vs remote install instructions
  const isLocal = !host || host === "localhost" || host === "127.0.0.1" || host === "::1";
  const deployBtn   = document.getElementById("signal-btn-deploy");
  const deployHint  = document.getElementById("signal-deploy-hint");
  const remoteBlock = document.getElementById("signal-remote-install");
  if (deployBtn)   deployBtn.style.display  = isLocal ? "" : "none";
  if (deployHint)  deployHint.style.display = isLocal ? "" : "none";
  if (remoteBlock) remoteBlock.classList.toggle("hidden", isLocal);

  if (!isLocal) {
    // Update remote host label and install command
    const hostSpan = document.getElementById("signal-remote-host");
    if (hostSpan) hostSpan.textContent = host;
    const cmdEl = document.getElementById("signal-cmd-remote");
    if (cmdEl) cmdEl.textContent = [
      `# Install Docker Engine`,
      `apt-get install -y docker.io`,
      `systemctl enable --now docker`,
      ``,
      `# Pull and start signal-cli-rest-api`,
      `mkdir -p /opt/signal`,
      `docker run -d --name signal-cli-rest-api \\`,
      `  --restart unless-stopped \\`,
      `  -p ${port}:8080 \\`,
      `  -v /opt/signal:/home/.local/share/signal-cli \\`,
      `  bbernhard/signal-cli-rest-api`,
    ].join("\n");
  }
}

function signalUpdateRegisterCmds() {
  const host    = (document.getElementById("signal-host")?.value.trim()) || "localhost";
  const port    = (document.getElementById("signal-port")?.value.trim()) || "8080";
  const from    = (document.getElementById("signal-from")?.value.trim()) || "";
  const captcha = (document.getElementById("signal-captcha-input")?.value.trim()) || "signalcaptcha://...";
  const sms     = (document.getElementById("signal-sms-code")?.value.trim()) || "123456";

  const fromEncoded = from ? encodeURIComponent(from) : "%2B33...";

  const el2 = document.getElementById("signal-cmd-register");
  if (el2) el2.textContent =
    `curl -X POST "http://${host}:${port}/v1/register/${fromEncoded}" \\\n` +
    `  -H 'Content-Type: application/json' \\\n` +
    `  -d '{"captcha": "${captcha}"}'`;

  const el3 = document.getElementById("signal-cmd-verify");
  if (el3) el3.textContent =
    `curl -X POST "http://${host}:${port}/v1/register/${fromEncoded}/verify/${sms}"`;
}

function signalCopyCmd(id) {
  const el = document.getElementById(id);
  if (!el) return;
  navigator.clipboard.writeText(el.textContent).then(
    () => showToast(t("copy_ok"), "ok"),
    () => showToast(t("copy_fail"), "error")
  );
}

async function signalCheck() {
  const host = document.getElementById("signal-host").value.trim() || "localhost";
  const port = parseInt(document.getElementById("signal-port").value.trim()) || 8080;
  const statusEl = document.getElementById("signal-status");
  statusEl.textContent = t("settings_checking");
  statusEl.className = "signal-status checking";
  try {
    const res = await API.post("/api/settings/check-signal", { host, port });
    if (res.running) {
      statusEl.textContent = t("signal_running") + (res.version ? ` v${res.version}` : "");
      statusEl.className = "signal-status ok";
    } else {
      statusEl.textContent = t("signal_unreachable");
      statusEl.className = "signal-status error";
    }
  } catch {
    statusEl.textContent = t("signal_unreachable");
    statusEl.className = "signal-status error";
  }
}

async function signalDeploy() {
  const port = parseInt(document.getElementById("signal-port").value.trim()) || 8080;
  const statusEl = document.getElementById("signal-status");
  const btn = document.getElementById("signal-btn-deploy");
  statusEl.textContent = t("signal_deploying");
  statusEl.className = "signal-status checking";
  if (btn) { btn.disabled = true; btn.textContent = t("signal_deploying"); }
  try {
    const res = await API.post("/api/settings/deploy-signal", { port });
    if (res.success) {
      const msgKey = res.action === "already_running" ? "signal_already_running" : "signal_deployed";
      statusEl.textContent = t(msgKey);
      statusEl.className = "signal-status ok";
      setTimeout(signalCheck, 2000);
    } else {
      statusEl.textContent = res.message || t("settings_error");
      statusEl.className = "signal-status error";
    }
  } catch {
    statusEl.textContent = t("settings_error");
    statusEl.className = "signal-status error";
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = t("signal_btn_deploy"); }
  }
}

async function signalRegister() {
  const host    = document.getElementById("signal-host").value.trim() || "localhost";
  const port    = parseInt(document.getElementById("signal-port").value.trim()) || 8080;
  const number  = document.getElementById("signal-from").value.trim();
  const captcha = document.getElementById("signal-captcha-input").value.trim();
  const statusEl = document.getElementById("signal-register-status");
  const btn = document.getElementById("signal-btn-register");
  if (!number) { showToast(t("signal_err_number"), "error"); return; }
  if (!captcha) { showToast(t("signal_err_captcha"), "error"); return; }
  statusEl.textContent = t("signal_register_running");
  statusEl.className = "signal-status checking";
  statusEl.style.display = "inline-flex";
  if (btn) btn.disabled = true;
  try {
    const res = await API.post("/api/settings/signal-register", { host, port, number, captcha });
    if (res.success) {
      statusEl.textContent = t("signal_sms_sent");
      statusEl.className = "signal-status ok";
    } else {
      statusEl.textContent = res.message || t("settings_error");
      statusEl.className = "signal-status error";
    }
  } catch(e) {
    statusEl.textContent = t("settings_error");
    statusEl.className = "signal-status error";
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function signalVerify() {
  const host   = document.getElementById("signal-host").value.trim() || "localhost";
  const port   = parseInt(document.getElementById("signal-port").value.trim()) || 8080;
  const number = document.getElementById("signal-from").value.trim();
  const code   = document.getElementById("signal-sms-code").value.trim();
  const statusEl = document.getElementById("signal-verify-status");
  const btn = document.getElementById("signal-btn-verify");
  if (!number) { showToast(t("signal_err_number"), "error"); return; }
  if (!code)   { showToast(t("signal_err_code"), "error"); return; }
  statusEl.textContent = t("signal_verify_running");
  statusEl.className = "signal-status checking";
  statusEl.style.display = "inline-flex";
  if (btn) btn.disabled = true;
  try {
    const res = await API.post("/api/settings/signal-verify", { host, port, number, code });
    if (res.success) {
      statusEl.textContent = t("signal_verified");
      statusEl.className = "signal-status ok";
      // Show persistent registration badge
      const badge = document.getElementById("signal-reg-status");
      if (badge) badge.classList.remove("hidden");
    } else {
      statusEl.textContent = res.message || t("settings_error");
      statusEl.className = "signal-status error";
    }
  } catch(e) {
    statusEl.textContent = t("settings_error");
    statusEl.className = "signal-status error";
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function signalReset() {
  if (!confirm(t("signal_reset_confirm"))) return;
  const host   = document.getElementById("signal-host")?.value.trim() || "localhost";
  const port   = parseInt(document.getElementById("signal-port")?.value.trim()) || 8080;
  const number = document.getElementById("signal-from")?.value.trim() || "";
  try {
    const res = await API.post("/api/settings/signal-reset", { host, port, number });
    if (res.success) {
      showToast(t("signal_reset_done"), "ok");
      // Clear fields and hide all Signal UI
      document.getElementById("signal-host").value = "";
      document.getElementById("signal-port").value = "8080";
      document.getElementById("signal-from").value = "";
      document.getElementById("signal-to").value = "";
      document.getElementById("webhook-url").value = "";
      document.getElementById("webhook-format").value = "generic";
      const badge = document.getElementById("signal-reg-status");
      if (badge) badge.classList.add("hidden");
      document.getElementById("signal-compact-view").classList.add("hidden");
      updateWebhookPreset();
    } else {
      showToast(res.message || t("settings_error"), "error");
    }
  } catch {
    showToast(t("settings_error"), "error");
  }
}

// ---- Signal compact / full panel ----

function signalShowCompactView() {
  const from = document.getElementById("signal-from").value.trim();
  const to   = document.getElementById("signal-to").value.trim();
  document.getElementById("signal-compact-from").textContent = from || "—";
  document.getElementById("signal-compact-to").textContent   = to   || "—";
  document.getElementById("signal-compact-to-input").value   = to;
  document.getElementById("signal-compact-view").classList.remove("hidden");
  document.getElementById("signal-config").classList.add("hidden");
}

function signalShowFullPanel() {
  document.getElementById("signal-compact-view").classList.add("hidden");
  document.getElementById("signal-config").classList.remove("hidden");
  const testBtn = document.getElementById("signal-btn-test-full");
  if (testBtn) testBtn.classList.remove("hidden");
  const regBadge = document.getElementById("signal-reg-status");
  if (regBadge) regBadge.classList.remove("hidden");
}

async function signalAutoDetectStatus() {
  try {
    const status = await API.get("/api/settings/signal-status");
    if (status.registered) {
      if (status.number_from && !document.getElementById("signal-from").value)
        document.getElementById("signal-from").value = status.number_from;
      if (status.number_to && !document.getElementById("signal-to").value)
        document.getElementById("signal-to").value = status.number_to;
      if (status.host && !document.getElementById("signal-host").value)
        document.getElementById("signal-host").value = status.host;
      if (status.port && !document.getElementById("signal-port").value)
        document.getElementById("signal-port").value = status.port;
      signalBuildUrl();
      signalShowCompactView();
    }
  } catch { /* silent */ }
}

// ---- Signal stepper ----

function signalStepSetState(n, state) {
  const step = document.getElementById(`signal-step-${n}`);
  const ind  = document.getElementById(`stepper-ind-${n}`);
  const num  = document.getElementById(`signal-step-num-${n}`);
  if (!step) return;
  step.className = `signal-stepper-step step--${state}`;
  if (ind) ind.className = `signal-step-indicator step-ind--${state}`;
  if (num) {
    if (state === "done") {
      num.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`;
      num.style.background = "var(--green, #22c55e)";
      num.style.color = "#fff";
    } else {
      num.textContent = n;
      num.style.background = "";
      num.style.color = "";
    }
  }
}

function signalStepUnlock(n) {
  if (n > 4) return;
  signalStepSetState(n, "active");
  const el = document.getElementById(`signal-step-${n}`);
  if (el) el.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function signalStepperReset() {
  signalStepSetState(1, "active");
  for (let i = 2; i <= 4; i++) signalStepSetState(i, "locked");
  ["signal-step1-status", "signal-step3-status", "signal-step4-status"].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.textContent = ""; el.className = "signal-status"; }
  });
}

async function signalStepCheckService() {
  const btn   = document.getElementById("signal-step1-btn");
  const badge = document.getElementById("signal-step1-status");
  const host  = document.getElementById("signal-host").value.trim() || "localhost";
  const port  = parseInt(document.getElementById("signal-port").value.trim()) || 8080;
  if (btn) btn.disabled = true;
  badge.textContent = t("settings_checking");
  badge.className = "signal-status checking";
  try {
    const res = await API.post("/api/settings/check-signal", { host, port });
    if (res.running) {
      badge.textContent = t("signal_running") + (res.version ? ` v${res.version}` : "");
      badge.className = "signal-status ok";
      signalStepSetState(1, "done");
      signalStepUnlock(2);
    } else {
      badge.textContent = t("signal_unreachable");
      badge.className = "signal-status error";
    }
  } catch {
    badge.textContent = t("signal_unreachable");
    badge.className = "signal-status error";
  } finally {
    if (btn) btn.disabled = false;
  }
}

function signalStepCaptchaValidate() {
  const captcha = document.getElementById("signal-captcha-input")?.value.trim() || "";
  if (captcha.startsWith("signalcaptcha://") && captcha.length > 20) {
    signalStepSetState(2, "done");
    signalStepUnlock(3);
  }
}

async function signalStepRegister() {
  const badge   = document.getElementById("signal-step3-status");
  const btn     = document.getElementById("signal-btn-register");
  const host    = document.getElementById("signal-host").value.trim() || "localhost";
  const port    = parseInt(document.getElementById("signal-port").value.trim()) || 8080;
  const number  = document.getElementById("signal-from").value.trim();
  const captcha = document.getElementById("signal-captcha-input").value.trim();
  if (!number)  { showToast(t("signal_err_number"),  "error"); return; }
  if (!captcha) { showToast(t("signal_err_captcha"), "error"); return; }
  badge.textContent = t("signal_register_running");
  badge.className = "signal-status checking";
  if (btn) btn.disabled = true;
  try {
    const res = await API.post("/api/settings/signal-register", { host, port, number, captcha });
    if (res.success) {
      badge.textContent = t("signal_sms_sent");
      badge.className = "signal-status ok";
      signalStepSetState(3, "done");
      signalStepUnlock(4);
      setTimeout(() => document.getElementById("signal-sms-code")?.focus(), 300);
    } else {
      badge.textContent = res.message || t("settings_error");
      badge.className = "signal-status error";
    }
  } catch {
    badge.textContent = t("settings_error");
    badge.className = "signal-status error";
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function signalStepVerify() {
  const badge  = document.getElementById("signal-step4-status");
  const btn    = document.getElementById("signal-btn-verify");
  const host   = document.getElementById("signal-host").value.trim() || "localhost";
  const port   = parseInt(document.getElementById("signal-port").value.trim()) || 8080;
  const number = document.getElementById("signal-from").value.trim();
  const code   = document.getElementById("signal-sms-code").value.trim().replace("-", "");
  if (!number) { showToast(t("signal_err_number"), "error"); return; }
  if (!code)   { showToast(t("signal_err_code"),   "error"); return; }
  badge.textContent = t("signal_verify_running");
  badge.className = "signal-status checking";
  if (btn) btn.disabled = true;
  try {
    const res = await API.post("/api/settings/signal-verify", { host, port, number, code });
    if (res.success) {
      badge.textContent = t("signal_verified");
      badge.className = "signal-status ok";
      signalStepSetState(4, "done");
      const regBadge = document.getElementById("signal-reg-status");
      if (regBadge) regBadge.classList.remove("hidden");
      showToast(t("signal_verified"), "ok");
      setTimeout(() => signalShowCompactView(), 1000);
    } else {
      badge.textContent = res.message || t("settings_error");
      badge.className = "signal-status error";
    }
  } catch {
    badge.textContent = t("settings_error");
    badge.className = "signal-status error";
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ---- Signal test & recipient update ----

async function signalSendTest() {
  showToast(t("signal_test_sending"), "ok");
  try {
    const res = await API.post("/api/settings/signal-test", {});
    if (res.success) {
      showToast(t("signal_test_ok"), "ok");
    } else {
      showToast(t("signal_test_fail") + " " + (res.message || ""), "error");
    }
  } catch (e) {
    showToast(t("error_prefix") + e.message, "error");
  }
}

async function signalUpdateRecipient() {
  const newTo = document.getElementById("signal-compact-to-input").value.trim();
  if (!newTo.match(/^\+[0-9]{7,15}$/)) {
    showToast(t("signal_err_number_format"), "error");
    return;
  }
  document.getElementById("signal-to").value = newTo;
  signalBuildUrl();
  const newUrl = document.getElementById("webhook-url").value;
  try {
    await API.put("/api/settings/", { webhook_url: newUrl, webhook_format: "signal", webhook_enabled: true });
    document.getElementById("signal-compact-to").textContent = newTo;
    showToast(t("signal_recipient_updated"), "ok");
  } catch (e) {
    showToast(t("error_prefix") + e.message, "error");
  }
}

// ---- Webhook test ----

async function testWebhook() {
  try {
    // Save webhook settings first
    await saveWebhookSettings();
    const res = await API.post("/api/settings/test-webhook", {});
    if (res.success) {
      showToast(t("webhook_sent"), "ok");
    } else {
      showToast(t("webhook_fail") + res.message, "error");
    }
  } catch (e) {
    showToast(t("error_prefix") + e.message, "error");
  }
}

async function saveWebhookSettings() {
  const events = [];
  if (document.getElementById("wh-evt-complete").checked) events.push("download_complete");
  if (document.getElementById("wh-evt-failed").checked) events.push("download_failed");
  if (document.getElementById("wh-evt-package").checked) events.push("package_complete");

  if (document.getElementById("webhook-format").value === "signal") signalBuildUrl();

  await API.put("/api/settings/", {
    webhook_enabled: document.getElementById("webhook-enabled").checked,
    webhook_url: document.getElementById("webhook-url").value.trim(),
    webhook_format: document.getElementById("webhook-format").value,
    webhook_events: events,
  });
}

async function saveWebhookDetails() {
  try {
    await saveWebhookSettings();
    showToast(t("settings_webhook_saved"), "ok");
  } catch (error) {
    showToast(t("error_prefix") + error.message, "error");
  }
}

// ---- Save all settings ----

async function saveSettings() {
  const resultEl = document.getElementById("save-result");
  resultEl.textContent = t("settings_saving");
  resultEl.className = "inline-result";

  // Collect webhook events
  const events = [];
  if (document.getElementById("wh-evt-complete").checked) events.push("download_complete");
  if (document.getElementById("wh-evt-failed").checked) events.push("download_failed");
  if (document.getElementById("wh-evt-package").checked) events.push("package_complete");

  if (document.getElementById("webhook-format").value === "signal") signalBuildUrl();

  const newAllDebridKey = document.getElementById("alldebrid-key").value.trim();
  const maxRetriesRaw = parseInt(document.getElementById("max-retries-input").value);
  const retryDelayRaw = parseInt(document.getElementById("retry-delay-input").value);
  const stalledTimeoutRaw = parseInt(document.getElementById("stalled-timeout-input").value);
  const payload = {
    alldebrid_api_key: newAllDebridKey || undefined,
    alldebrid_enabled: document.getElementById("alldebrid-enabled").checked,
    simultaneous_downloads: Math.min(20, Math.max(1, parseInt(document.getElementById("simultaneous-input").value) || 3)),
    download_segments: Math.min(16, Math.max(1, parseInt(document.getElementById("segments-input").value) || 1)),
    speed_limit: parseInt(document.getElementById("speed-limit").value) || 0,
    max_retries: Math.min(20, Math.max(0, Number.isNaN(maxRetriesRaw) ? 3 : maxRetriesRaw)),
    retry_delay_seconds: Math.min(3600, Math.max(0, Number.isNaN(retryDelayRaw) ? 5 : retryDelayRaw)),
    stalled_timeout_hours: Math.min(168, Math.max(0, Number.isNaN(stalledTimeoutRaw) ? 3 : stalledTimeoutRaw)),
    default_destination: document.getElementById("default-dest").value.trim() || undefined,
    webhook_enabled: document.getElementById("webhook-enabled").checked,
    webhook_url: document.getElementById("webhook-url").value.trim() || undefined,
    webhook_format: document.getElementById("webhook-format").value,
    webhook_events: events,
    youtube_direct_enabled: document.getElementById("youtube-direct-enabled").checked,
    youtube_max_concurrent: Math.min(4, Math.max(1, parseInt(document.getElementById("youtube-concurrency").value) || 2)),
    youtube_speed_limit: Math.max(0, parseInt(document.getElementById("youtube-speed-limit").value) || 0),
  };

  Object.keys(payload).forEach((k) => payload[k] === undefined && delete payload[k]);

  try {
    await API.put("/api/settings/", payload);
    await saveMedia();
    if (newAllDebridKey) {
      window._alldebridKeyConfigured = true;
      document.getElementById("alldebrid-key").value = "";
    }
    document.getElementById("plex-token").value = "";
    document.getElementById("jellyfin-token").value = "";
    await refreshAllDebridHosts();
    await loadMediaSettings();
    resultEl.textContent = t("settings_saved");
    resultEl.className = "inline-result ok";
    showToast(t("settings_all_saved"), "ok");
  } catch (e) {
    resultEl.textContent = t("settings_error");
    resultEl.className = "inline-result error";
    let msg = e.message;
    try { msg = JSON.parse(e.message).detail; } catch {}
    showToast(t("error_prefix") + msg, "error");
  }
}

// ---- Toast ----

let _toastTimer = null;
function showToast(msg, type = "ok") {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className = `toast ${type}`;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.add("hidden"), 3500);
}

// ---- Auth check for settings page ----

async function checkSettingsAuth() {
  try {
    const status = await fetch("/api/auth/status").then(r => r.json());

    if (!status.admin_exists) {
      window.location.href = "/";
      return false;
    }

    const check = await fetch("/api/settings/", { credentials: "same-origin" });
    if (check.status === 401) {
      showSettingsLogin();
      return false;
    }
    return true;
  } catch {
    return true;
  }
}

function showSettingsLogin() {
  document.getElementById("login-modal").classList.remove("hidden");
  document.getElementById("login-form").classList.remove("hidden");
  document.getElementById("otp-group").classList.add("hidden");
  document.getElementById("login-otp").value = "";
  document.getElementById("login-error").classList.add("hidden");
}

let _settingsOtpRequired = false;

async function doSettingsLogin() {
  const username = document.getElementById("login-username").value;
  const password = document.getElementById("login-password").value;
  const otpCode  = document.getElementById("login-otp").value.trim();
  const errEl    = document.getElementById("login-error");

  errEl.classList.add("hidden");

  const body = { username, password };
  if (_settingsOtpRequired && otpCode) {
    body.otp_code = otpCode;
  }

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
      if (_settingsOtpRequired) {
        document.getElementById("login-otp").value = "";
        document.getElementById("login-otp").focus();
      }
      return;
    }
    const data = await resp.json();

    if (data.otp_required) {
      _settingsOtpRequired = true;
      document.getElementById("otp-group").classList.remove("hidden");
      document.getElementById("login-otp").value = "";
      document.getElementById("login-otp").focus();
      return;
    }

    _settingsOtpRequired = false;
    localStorage.removeItem("dm_token");
    API.token = "";
    document.getElementById("login-modal").classList.add("hidden");
    bootSettings();
  } catch {
    errEl.textContent = t("settings_login_server_error");
    errEl.classList.remove("hidden");
  }
}

// Enter key support for login
document.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !document.getElementById("login-modal").classList.contains("hidden")) {
    doSettingsLogin();
  }
});

// ============================================================
//  SMB / Network Shares
// ============================================================

async function smbLoad() {
  try {
    const shares = await API.get("/api/smb/");
    smbRender(shares);
  } catch {
    document.getElementById("smb-list").innerHTML =
      `<p style="color:var(--text-3);font-size:13px">${t("smb_load_error")}</p>`;
  }
}

function smbRender(shares) {
  const el = document.getElementById("smb-list");
  if (!shares || shares.length === 0) {
    el.innerHTML = `<p class="form-hint" style="margin-bottom:0">${t("smb_empty")}</p>`;
    return;
  }
  el.innerHTML = shares.map(s => {
    const mounted = s.mounted;
    const badgeCls = mounted ? "conn-badge ok" : "conn-badge unknown";
    const badgeTxt = mounted ? t("smb_mounted") : t("smb_unmounted");
    const mountBtn = mounted
      ? `<button class="btn btn-sm" onclick="smbToggle('${s.name}','unmount')">${t("smb_btn_unmount")}</button>`
      : `<button class="btn btn-sm btn-primary" onclick="smbToggle('${s.name}','mount')">${t("smb_btn_mount")}</button>`;
    return `
      <div class="smb-share-row" id="smb-row-${s.name}">
        <div class="smb-share-info">
          <span class="smb-share-name">${_esc(s.name)}</span>
          <span class="smb-share-path">//${_esc(s.host)}/${_esc(s.share)}</span>
          <span class="smb-share-mp">${_esc(s.mount_point)}</span>
          <span class="${badgeCls}"><span class="b-dot"></span>${badgeTxt}</span>
        </div>
        <div class="smb-share-actions">
          ${mountBtn}
          <button class="btn btn-sm btn-danger" onclick="smbDelete('${s.name}')">${t("smb_btn_delete")}</button>
        </div>
      </div>`;
  }).join("");
}

function _esc(s) {
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

async function smbAddShare() {
  const name   = document.getElementById("smb-new-name").value.trim();
  const host   = document.getElementById("smb-new-host").value.trim();
  const share  = document.getElementById("smb-new-share").value.trim();
  const user   = document.getElementById("smb-new-user").value.trim();
  const pass   = document.getElementById("smb-new-pass").value;
  const domain = document.getElementById("smb-new-domain").value.trim();
  const vers   = document.getElementById("smb-new-vers").value;
  const auto   = document.getElementById("smb-new-auto").checked;

  if (!name || !host || !share) {
    showToast(t("smb_fields_required"), "error");
    return;
  }
  try {
    await API.post("/api/smb/", { name, host, share, username: user, password: pass, domain, vers, auto_mount: auto });
    showToast(t("smb_added"), "ok");
    ["smb-new-name","smb-new-host","smb-new-share","smb-new-user","smb-new-pass","smb-new-domain"].forEach(id => {
      document.getElementById(id).value = "";
    });
    document.getElementById("smb-new-vers").value = "";
    document.getElementById("smb-new-auto").checked = true;
    document.getElementById("smb-add-details").removeAttribute("open");
    await smbLoad();
  } catch (e) {
    let msg = e.message;
    try { msg = JSON.parse(e.message).detail; } catch {}
    showToast(t("error_prefix") + msg, "error");
  }
}

async function smbToggle(name, action) {
  try {
    const res = await API.post(`/api/smb/${name}/${action}`, {});
    if (res.success) {
      showToast(action === "mount" ? t("smb_mount_ok") : t("smb_unmount_ok"), "ok");
    } else {
      showToast(t("smb_mount_fail") + ": " + res.message, "error");
    }
    await smbLoad();
  } catch (e) {
    showToast(t("error_prefix") + e.message, "error");
  }
}

async function smbDelete(name) {
  if (!confirm(t("smb_confirm_delete") + " \"" + name + "\"?")) return;
  try {
    await API.del(`/api/smb/${name}`);
    showToast(t("smb_deleted"), "ok");
    await smbLoad();
  } catch (e) {
    showToast(t("error_prefix") + e.message, "error");
  }
}

// ============================================================
//  Storage
// ============================================================

async function loadStorage() {
  const el = document.getElementById("storage-list");
  if (!el) return;
  el.innerHTML = `<p class="form-hint">${t("settings_checking")}</p>`;
  try {
    const items = await API.get("/api/settings/storage");
    if (!items || items.length === 0) {
      el.innerHTML = `<p class="form-hint" style="margin-bottom:0">${t("storage_empty")}</p>`;
      return;
    }
    el.innerHTML = items.map(item => {
      const pathEsc = _esc(item.path);
      const deleteBtn = `<button class="storage-delete" onclick="storageRemove('${pathEsc}')" title="${t('storage_btn_remove')}">
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>`;
      if (!item.available) {
        return `
          <div class="storage-row">
            <span class="storage-path" title="${pathEsc}">${pathEsc}</span>
            <span class="storage-numbers" style="color:var(--text-3)">${t("storage_unavailable")}</span>
            ${deleteBtn}
            <div class="storage-bar-wrap"><div class="storage-bar" style="width:0%"></div></div>
          </div>`;
      }
      const pct = item.percent;
      const color = pct >= 90 ? "var(--red)" : pct >= 70 ? "var(--orange, #f97316)" : "var(--green)";
      return `
        <div class="storage-row">
          <span class="storage-path" title="${pathEsc}">${pathEsc}</span>
          <span class="storage-numbers">${formatSize(item.used)} / ${formatSize(item.total)} (${pct}%)</span>
          ${deleteBtn}
          <div class="storage-bar-wrap"><div class="storage-bar" style="width:${pct}%;background:${color}"></div></div>
        </div>`;
    }).join("");
  } catch {
    el.innerHTML = `<p class="form-hint" style="color:var(--red)">${t("settings_error")}</p>`;
  }
}

function storageOpenBrowser() {
  FileBrowser.open(async (path) => {
    if (!path) return;
    try {
      await API.post("/api/settings/storage/paths", { path });
      showToast(t("storage_added"), "ok");
      await loadStorage();
    } catch (e) {
      showToast(t("error_prefix") + e.message, "error");
    }
  });
}

async function storageRemove(path) {
  try {
    await API.del("/api/settings/storage/paths", { path });
    showToast(t("storage_removed"), "ok");
    await loadStorage();
  } catch (e) {
    showToast(t("error_prefix") + e.message, "error");
  }
}

// ---- Boot ----

function initSettingsSections() {
  document.querySelectorAll(".settings-card[data-settings-section]").forEach((card) => {
    const title = card.querySelector(".card-title");
    const section = card.getAttribute("data-settings-section");
    if (!title || !section || title.dataset.collapseBound === "1") return;

    const storageKey = "dm_settings_section_" + section;
    const saved = localStorage.getItem(storageKey);
    const defaultOpen = card.getAttribute("data-default-open") === "true";
    const startOpen = saved ? saved === "open" : defaultOpen;

    title.dataset.collapseBound = "1";
    title.setAttribute("role", "button");
    title.setAttribute("tabindex", "0");
    title.setAttribute("aria-expanded", startOpen ? "true" : "false");

    const chevron = document.createElement("span");
    chevron.className = "settings-section-chevron";
    chevron.setAttribute("aria-hidden", "true");
    chevron.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>';
    title.appendChild(chevron);

    function setOpen(open, persist) {
      card.classList.toggle("collapsed", !open);
      title.setAttribute("aria-expanded", open ? "true" : "false");
      if (persist) localStorage.setItem(storageKey, open ? "open" : "closed");
    }

    function toggle() {
      setOpen(card.classList.contains("collapsed"), true);
    }

    title.addEventListener("click", toggle);
    title.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        toggle();
      }
    });

    setOpen(startOpen, false);
  });
}

function initInlineHelpDismiss() {
  if (document.body.dataset.inlineHelpDismissBound === "1") return;
  document.body.dataset.inlineHelpDismissBound = "1";

  document.addEventListener("click", (event) => {
    document.querySelectorAll("details.inline-help[open]").forEach((details) => {
      if (!details.contains(event.target)) details.open = false;
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    document.querySelectorAll("details.inline-help[open]").forEach((details) => {
      details.open = false;
    });
  });
}

async function bootSettings() {
  initSettingsSections();
  initInlineHelpDismiss();

  try {
    const cfg = await API.get("/api/settings/");

    window._alldebridKeyConfigured = !!cfg.alldebrid_api_key_configured;
    const adInput = document.getElementById("alldebrid-key");
    adInput.value = "";
    adInput.placeholder = window._alldebridKeyConfigured
      ? "Configured - enter a new key to replace"
      : (cfg.alldebrid_api_key || "");
    document.getElementById("alldebrid-enabled").checked = cfg.alldebrid_enabled || false;
    document.getElementById("default-dest").value        = cfg.default_destination || "";
    // Webhooks
    document.getElementById("webhook-enabled").checked = cfg.webhook_enabled || false;
    document.getElementById("webhook-url").value = cfg.webhook_url || "";
    document.getElementById("webhook-format").value = cfg.webhook_format || "generic";
    if (cfg.webhook_events) {
      document.getElementById("wh-evt-complete").checked = cfg.webhook_events.includes("download_complete");
      document.getElementById("wh-evt-failed").checked = cfg.webhook_events.includes("download_failed");
      document.getElementById("wh-evt-package").checked = cfg.webhook_events.includes("package_complete");
    }
    toggleWebhookFields();
    // Auto-detect Signal status and switch to compact view if registered
    if (cfg.signal_registered || cfg.webhook_format === "signal") {
      await signalAutoDetectStatus();
    }

    document.getElementById("simultaneous-input").value = cfg.simultaneous_downloads || 3;
    document.getElementById("segments-input").value = cfg.download_segments || 1;
    document.getElementById("speed-limit").value = cfg.speed_limit || 0;
    loadSpeedLimitStatus();
    document.getElementById("max-retries-input").value = cfg.max_retries ?? 3;
    document.getElementById("retry-delay-input").value = cfg.retry_delay_seconds ?? 5;
    document.getElementById("stalled-timeout-input").value = cfg.stalled_timeout_hours ?? 3;
    document.getElementById("skip-nfo-files").checked = cfg.skip_nfo_files !== false;
    document.getElementById("youtube-direct-enabled").checked = cfg.youtube_direct_enabled === true;
    document.getElementById("youtube-concurrency").value = cfg.youtube_max_concurrent || 2;
    document.getElementById("youtube-speed-limit").value = cfg.youtube_speed_limit || 0;

    await checkAllDebridStatus();
    await refreshAllDebridHosts();
    await loadYouTubeStatus();

    // Load current version
    try {
      const ver = await API.get("/api/settings/version");
      document.getElementById("current-version").textContent = "v" + ver.version;
    } catch {}

    // Show account button if auth is enabled
    if (typeof initAccountButton === "function") initAccountButton();

    // Load SMB shares
    await smbLoad();

    // Load storage info
    await loadStorage();

    // Load Plex configuration
    await loadPlexSettings();

    // Load runtime diagnostics
    await loadDiagnostics();
  } catch {
    showToast(t("settings_load_error"), "error");
  }
}

// ---- Diagnostics ----

function diagnosticsHelp(textKey) {
  return `
    <details class="inline-help diagnostics-help">
      <summary aria-label="${escHtml(t("diagnostics_help_label"))}">i</summary>
      <div class="inline-help-box">${escHtml(t(textKey))}</div>
    </details>`;
}

function diagnosticsBadge(level, labelKey) {
  return `<span class="diagnostics-badge ${escHtml(level)}">${escHtml(t(labelKey))}</span>`;
}

function diagnosticsMetric(labelKey, value, helpKey) {
  return `
    <div class="diagnostics-metric">
      <span>${escHtml(t(labelKey))}</span>
      ${diagnosticsHelp(helpKey)}
      <strong>${escHtml(String(value))}</strong>
    </div>`;
}

function diagnosticsSection(titleKey, level, badgeKey, summary, metricsHtml) {
  return `
    <section class="diagnostics-item diagnostics-${escHtml(level)}">
      <div class="diagnostics-item-head">
        <div>
          <strong>${escHtml(t(titleKey))}</strong>
          <p>${escHtml(summary)}</p>
        </div>
        ${diagnosticsBadge(level, badgeKey)}
      </div>
      <div class="diagnostics-metrics">${metricsHtml}</div>
    </section>`;
}

function diagnosticsTableLabel(name) {
  const map = {
    downloads: "diagnostics_table_downloads",
    packages: "diagnostics_table_packages",
    torrents: "diagnostics_table_torrents",
    history: "diagnostics_table_history",
    users: "diagnostics_table_users",
    blocked_ips: "diagnostics_table_blocked_ips",
  };
  return t(map[name] || "diagnostics_table_unknown", { name });
}

function diagnosticsStatusLabel(status) {
  const map = {
    pending: "diagnostics_status_pending",
    submitting: "diagnostics_status_submitting",
    downloading: "diagnostics_status_downloading",
    postprocessing: "status_postprocessing",
    paused: "diagnostics_status_paused",
    error: "diagnostics_status_error",
    failed: "diagnostics_status_failed",
    complete: "diagnostics_status_complete",
  };
  return t(map[status] || "diagnostics_status_unknown", { status });
}

function renderDiagnostics(data) {
  const panel = document.getElementById("diagnostics-panel");
  if (!panel) return;

  const queue = data.queue || {};
  const aria2 = data.aria2 || {};
  const db = data.database || {};
  const tables = db.tables || {};
  const statuses = db.download_statuses || [];
  const recent = data.events || queue.recent_errors || [];

  const tick = Number(queue.last_tick_seconds || 0);
  const tempErrors = Number(queue.temporary_aria2_errors || 0);
  const blockedIps = Number(tables.blocked_ips || 0);
  const queueLevel = !queue.running || tick > 5 || tempErrors >= 10 ? "bad" : (tick > 2 || tempErrors > 0 ? "warn" : "ok");
  const queueBadge = queueLevel === "bad" ? "diagnostics_state_bad" : (queueLevel === "warn" ? "diagnostics_state_warn" : "diagnostics_state_ok");
  const queueSummary = queueLevel === "bad" ? t("diagnostics_queue_bad") : (queueLevel === "warn" ? t("diagnostics_queue_warn") : t("diagnostics_queue_ok"));

  const ariaLevel = aria2.ok ? "ok" : "bad";
  const dbLevel = blockedIps > 0 ? "warn" : "ok";
  const errorsLevel = recent.length ? "warn" : "ok";

  const tableMetrics = Object.entries(tables).map(([name, count]) =>
    diagnosticsMetric("diagnostics_metric_table", `${diagnosticsTableLabel(name)}: ${count}`, "diagnostics_help_db_tables")
  ).join("");
  const statusMetrics = statuses.length ? statuses.map((item) =>
    diagnosticsMetric("diagnostics_metric_status", `${diagnosticsStatusLabel(item.status)}: ${item.count}`, "diagnostics_help_db_statuses")
  ).join("") : diagnosticsMetric("diagnostics_metric_status", t("diagnostics_none"), "diagnostics_help_db_statuses");
  const recentErrors = recent.length
    ? recent.slice(0, 5).map((error) => `
        <div class="diagnostics-error-line">
          <span>${escHtml(error.created_at || error.at || "")}</span>
          <strong>${escHtml(error.source || "")}${error.code ? ` · ${escHtml(error.code)}` : ""}</strong>
          <span>${escHtml(error.message || "")}</span>
        </div>`).join("")
    : `<div class="diagnostics-error-line">${escHtml(t("diagnostics_no_recent_errors"))}</div>`;

  panel.innerHTML = `
    <div class="diagnostics-list">
      ${diagnosticsSection("diagnostics_queue", queueLevel, queueBadge, queueSummary, [
        diagnosticsMetric("diagnostics_metric_running", queue.running ? t("diagnostics_yes") : t("diagnostics_no"), "diagnostics_help_queue_running"),
        diagnosticsMetric("diagnostics_metric_last_tick", `${tick}s`, "diagnostics_help_queue_tick"),
        diagnosticsMetric("diagnostics_metric_active", queue.active_downloads || 0, "diagnostics_help_queue_active"),
        diagnosticsMetric("diagnostics_metric_pending", queue.pending_downloads || 0, "diagnostics_help_queue_pending"),
        diagnosticsMetric("diagnostics_metric_temp_errors", tempErrors, "diagnostics_help_queue_temp_errors"),
      ].join(""))}
      ${diagnosticsSection("diagnostics_aria2", ariaLevel, aria2.ok ? "diagnostics_state_ok" : "diagnostics_state_bad", aria2.ok ? t("diagnostics_aria2_ok") : t("diagnostics_aria2_bad"), aria2.ok ? [
        diagnosticsMetric("diagnostics_metric_active", aria2.active || 0, "diagnostics_help_aria_active"),
        diagnosticsMetric("diagnostics_metric_waiting", aria2.waiting || 0, "diagnostics_help_aria_waiting"),
        diagnosticsMetric("diagnostics_metric_stopped", aria2.stopped || 0, "diagnostics_help_aria_stopped"),
      ].join("") : diagnosticsMetric("diagnostics_metric_error", aria2.error || t("diagnostics_unknown_error"), "diagnostics_help_aria_error"))}
      ${diagnosticsSection("diagnostics_database", dbLevel, dbLevel === "warn" ? "diagnostics_state_warn" : "diagnostics_state_ok", dbLevel === "warn" ? t("diagnostics_database_warn") : t("diagnostics_database_ok"), tableMetrics + statusMetrics)}
      ${diagnosticsSection("diagnostics_recent_errors", errorsLevel, errorsLevel === "warn" ? "diagnostics_state_warn" : "diagnostics_state_ok", errorsLevel === "warn" ? t("diagnostics_errors_warn") : t("diagnostics_errors_ok"), `
        <div class="diagnostics-errors">
          ${diagnosticsHelp("diagnostics_help_recent_errors")}
          ${recentErrors}
        </div>`)}
    </div>`;
}

async function loadDiagnostics() {
  const panel = document.getElementById("diagnostics-panel");
  if (!panel) return;
  panel.innerHTML = `<p class="form-hint">${t("diagnostics_loading")}</p>`;
  try {
    const data = await API.get("/api/settings/diagnostics");
    renderDiagnostics(data);
  } catch (e) {
    panel.innerHTML = `<p class="form-hint" style="color:var(--red)">${t("diagnostics_unavailable")}: ${escHtml(e.message)}</p>`;
  }
}

async function clearDiagnosticEvents() {
  if (!confirm(getLang() === "fr" ? "Effacer le journal de diagnostic ?" : "Clear the diagnostic event log?")) return;
  try {
    await API.del("/api/settings/diagnostics/events");
    await loadDiagnostics();
    showToast(getLang() === "fr" ? "Journal effacé" : "Diagnostic log cleared", "ok");
  } catch (error) {
    showToast(t("error_prefix") + error.message, "error");
  }
}

// ---- Update system ----

function setUpdateBadge(state, text) {
  const badge = document.getElementById("update-badge");
  const label = document.getElementById("update-badge-text");
  badge.className = `conn-badge ${state}`;
  label.textContent = text;
}

function renderChangelog(md) {
  // Simple markdown → HTML (headers, bold, lists, line breaks)
  if (!md) return "";
  return md
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/^### (.+)$/gm, '<h4 style="margin:8px 0 4px;font-size:13px;color:var(--text)">$1</h4>')
    .replace(/^## (.+)$/gm, '<h3 style="margin:10px 0 6px;font-size:14px;color:var(--text)">$1</h3>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^- (.+)$/gm, '<div style="padding-left:12px;position:relative"><span style="position:absolute;left:0">•</span> $1</div>')
    .replace(/\n\n/g, '<br>')
    .replace(/`([^`]+)`/g, '<code style="background:var(--surface-3);padding:1px 5px;border-radius:3px;font-size:12px">$1</code>');
}

async function checkForUpdate() {
  const btn = document.getElementById("btn-check-update");
  btn.disabled = true;
  btn.textContent = t("update_checking");
  setUpdateBadge("checking", t("update_checking"));

  try {
    const res = await API.get("/api/settings/check-update");
    document.getElementById("current-version").textContent = "v" + res.current;

    if (res.error) {
      setUpdateBadge("error", res.message || t("settings_error"));
      document.getElementById("btn-do-update").classList.add("hidden");
      document.getElementById("update-info").classList.add("hidden");
      showToast(res.message || t("settings_error"), "error");
      return;
    }

    if (res.update_available) {
      setUpdateBadge("error", t("update_available", { v: res.latest }));
      document.getElementById("btn-do-update").classList.remove("hidden");
      document.getElementById("btn-do-update").textContent = t("update_btn_prefix") + res.latest;

      // Show changelog
      if (res.changelog) {
        document.getElementById("update-info").classList.remove("hidden");
        document.getElementById("update-changelog").innerHTML =
          '<p style="font-size:12px;color:var(--text-3);margin-bottom:6px;font-weight:600;text-transform:uppercase;letter-spacing:.5px">' + t("update_release_notes") + escHtml(res.latest) + '</p>' +
          '<div style="font-size:13px;color:var(--text-2);line-height:1.5">' + renderChangelog(res.changelog) + '</div>';
      }
      showToast(t("update_available_toast") + res.latest, "ok");
    } else {
      setUpdateBadge("ok", t("update_uptodate"));
      document.getElementById("btn-do-update").classList.add("hidden");
      document.getElementById("update-info").classList.add("hidden");
      showToast(res.message || t("update_uptodate"), "ok");
    }
  } catch (e) {
    setUpdateBadge("error", t("settings_error"));
    showToast(t("error_prefix") + e.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = t("update_check_btn");
  }
}

async function performUpdate() {
  const btn = document.getElementById("btn-do-update");
  btn.disabled = true;
  const origText = btn.textContent;
  btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="animation:spin 1s linear infinite"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg> ' + t("update_updating");
  setUpdateBadge("checking", t("update_updating"));

  try {
    const res = await API.post("/api/settings/update", {});
    if (res.success) {
      setUpdateBadge("checking", t("update_updating"));
      showToast(res.message, "ok");
      btn.textContent = t("update_restarting");

      // The updater runs outside this service and persists its status across restarts.
      setTimeout(() => {
        const poll = setInterval(async () => {
          try {
            const r = await fetch("/api/settings/update-status", {
              headers: API._headers(),
            });
            if (r.ok) {
              const status = await r.json();
              if (status.job_id !== res.job_id) return;
              if (status.state === "success") {
                clearInterval(poll);
                window.location.reload();
              } else if (status.state === "rolled_back" || status.state === "failed") {
                clearInterval(poll);
                setUpdateBadge("error", status.state === "rolled_back" ? "Rollback" : t("update_failed"));
                showToast(status.message || t("update_failed"), "error");
                btn.disabled = false;
                btn.textContent = origText;
              } else {
                setUpdateBadge("checking", status.message || t("update_updating"));
              }
            }
          } catch {}
        }, 1500);
        setTimeout(() => {
          clearInterval(poll);
          btn.disabled = false;
          btn.textContent = origText;
        }, 180000);
      }, 2000);
    } else {
      setUpdateBadge("error", t("update_failed"));
      showToast(res.message || t("update_failed"), "error");
      btn.disabled = false;
      btn.textContent = origText;
    }
  } catch (e) {
    setUpdateBadge("error", t("update_failed"));
    showToast(t("error_prefix") + e.message, "error");
    btn.disabled = false;
    btn.textContent = origText;
  }
}

// ---- Boot ----

(async () => {
  const authed = await checkSettingsAuth();
  if (authed) bootSettings();
})();
