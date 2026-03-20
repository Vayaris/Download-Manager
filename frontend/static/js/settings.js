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
  if (!key) { setAllDebridBadge("unknown", t("settings_not_configured")); return; }
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
  try {
    await API.put("/api/settings/", { alldebrid_api_key: key, alldebrid_enabled: enabled });
    showToast(t("settings_alldebrid_saved"), "ok");
    await checkAllDebridStatus();
  } catch (e) {
    showToast(t("error_prefix") + e.message, "error");
  }
}

// ---- Other settings ----

async function saveDownloadSettings() {
  const simultaneous = Math.min(10, Math.max(1, parseInt(document.getElementById("simultaneous-input").value) || 3));
  const segments = Math.min(8, Math.max(1, parseInt(document.getElementById("segments-input").value) || 1));
  const speedLimit = parseInt(document.getElementById("speed-limit").value) || 0;
  const dest = document.getElementById("default-dest").value.trim() || undefined;

  // Clamp input values visually
  document.getElementById("simultaneous-input").value = simultaneous;
  document.getElementById("segments-input").value = segments;

  try {
    await API.put("/api/settings/", {
      simultaneous_downloads: simultaneous,
      download_segments: segments,
      speed_limit: speedLimit,
      default_destination: dest,
    });
    showToast(t("settings_downloads_saved"), "ok");
  } catch (e) {
    showToast(t("error_prefix") + e.message, "error");
  }
}

function toggleKeyVisibility() {
  const input = document.getElementById("alldebrid-key");
  input.type = input.type === "password" ? "text" : "password";
}

function toggleWebhookFields() {
  const enabled = document.getElementById("webhook-enabled").checked;
  document.getElementById("webhook-fields").classList.toggle("hidden", !enabled);
  if (enabled) updateWebhookPreset();
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
  const el2 = document.getElementById("signal-cmd-register");
  if (el2) el2.textContent = `curl -X POST http://${host}:${port}/v1/register -H 'Content-Type: application/json' -d '{"number": "${fromNum}"}'`;
  const el3 = document.getElementById("signal-cmd-verify");
  if (el3) el3.textContent = `curl -X POST http://${host}:${port}/v1/verify/${fromNum} -d '{"token": "123456"}'`;

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
      `apt-get install -y default-jre`,
      ``,
      `# Install signal-cli`,
      `VER=$(curl -s https://api.github.com/repos/AsamK/signal-cli/releases/latest | grep -oP '"tag_name": "\\K[^"]+')`,
      `wget -q "https://github.com/AsamK/signal-cli/releases/download/$VER/signal-cli-${"{VER#v}"}.tar.gz" -O /tmp/signal-cli.tar.gz`,
      `tar -xf /tmp/signal-cli.tar.gz -C /opt && ln -sf /opt/signal-cli-*/bin/signal-cli /usr/local/bin/signal-cli`,
      ``,
      `# Install signal-cli-rest-api`,
      `APIVER=$(curl -s https://api.github.com/repos/bbernhard/signal-cli-rest-api/releases/latest | grep -oP '"tag_name": "\\K[^"]+')`,
      `wget -q "https://github.com/bbernhard/signal-cli-rest-api/releases/download/$APIVER/signal-cli-rest-api-amd64" -O /usr/local/bin/signal-cli-rest-api`,
      `chmod +x /usr/local/bin/signal-cli-rest-api`,
      ``,
      `# Create and start the service`,
      `mkdir -p /opt/signal`,
      `cat > /etc/systemd/system/signal-cli-rest-api.service << 'EOF'`,
      `[Unit]`,
      `Description=signal-cli REST API`,
      `After=network.target`,
      `[Service]`,
      `Type=simple`,
      `ExecStart=/usr/local/bin/signal-cli-rest-api -p ${port}`,
      `Environment=PATH=/usr/local/bin:/usr/bin:/bin`,
      `Environment=SIGNAL_CLI_CONFIG_DIR=/opt/signal`,
      `WorkingDirectory=/opt/signal`,
      `Restart=on-failure`,
      `[Install]`,
      `WantedBy=multi-user.target`,
      `EOF`,
      `systemctl daemon-reload && systemctl enable --now signal-cli-rest-api`,
    ].join("\n");
  }
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

  const payload = {
    alldebrid_api_key: document.getElementById("alldebrid-key").value.trim() || undefined,
    alldebrid_enabled: document.getElementById("alldebrid-enabled").checked,
    simultaneous_downloads: Math.min(10, Math.max(1, parseInt(document.getElementById("simultaneous-input").value) || 3)),
    download_segments: Math.min(8, Math.max(1, parseInt(document.getElementById("segments-input").value) || 1)),
    speed_limit: parseInt(document.getElementById("speed-limit").value) || 0,
    default_destination: document.getElementById("default-dest").value.trim() || undefined,
    webhook_enabled: document.getElementById("webhook-enabled").checked,
    webhook_url: document.getElementById("webhook-url").value.trim() || undefined,
    webhook_format: document.getElementById("webhook-format").value,
    webhook_events: events,
  };

  Object.keys(payload).forEach((k) => payload[k] === undefined && delete payload[k]);

  try {
    await API.put("/api/settings/", payload);
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

    const token = getAuthToken();
    if (!token) { showSettingsLogin(); return false; }

    // Validate token with raw fetch
    const check = await fetch("/api/settings/", {
      headers: { "Authorization": `Bearer ${token}` },
    });
    if (check.status === 401) {
      localStorage.removeItem("dm_token");
      API.token = "";
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
    localStorage.setItem("dm_token", data.token);
    API.token = data.token;
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
      const usedGb = (item.used / 1e9).toFixed(1);
      const totalGb = (item.total / 1e9).toFixed(1);
      return `
        <div class="storage-row">
          <span class="storage-path" title="${pathEsc}">${pathEsc}</span>
          <span class="storage-numbers">${usedGb} GB / ${totalGb} GB (${pct}%)</span>
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

async function bootSettings() {
  try {
    const cfg = await API.get("/api/settings/");

    document.getElementById("alldebrid-key").value      = cfg.alldebrid_api_key || "";
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

    document.getElementById("simultaneous-input").value = cfg.simultaneous_downloads || 3;
    document.getElementById("segments-input").value = cfg.download_segments || 1;
    document.getElementById("speed-limit").value = cfg.speed_limit || 0;

    await checkAllDebridStatus();

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
  } catch {
    showToast(t("settings_load_error"), "error");
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
      setUpdateBadge("ok", "v" + res.version);
      showToast(res.message, "ok");
      btn.textContent = t("update_restarting");

      // Wait for the service to restart, then reload
      setTimeout(() => {
        const poll = setInterval(async () => {
          try {
            const r = await fetch("/api/settings/version", {
              headers: API._headers(),
            });
            if (r.ok) {
              clearInterval(poll);
              window.location.reload();
            }
          } catch {}
        }, 1500);
        // Stop polling after 30s
        setTimeout(() => clearInterval(poll), 30000);
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
