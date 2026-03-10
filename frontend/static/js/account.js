// ============================================================
//  Account management — shared across pages
// ============================================================

// ---- Inject account modal HTML into page ----

(function injectAccountModal() {
  const html = `
<div id="account-modal" class="modal-overlay hidden" onclick="if(event.target===this)closeAccountModal()">
  <div class="modal-box" style="max-width:460px">
    <div class="modal-header">
      <div class="modal-header-title">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
        <h3>Mon compte</h3>
      </div>
      <button class="btn btn-icon" onclick="closeAccountModal()">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
    </div>
    <div style="padding:20px">

      <!-- User info -->
      <div class="acct-section">
        <div class="acct-user-row">
          <div class="acct-avatar">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
          </div>
          <div>
            <div class="acct-username" id="acct-username">—</div>
            <div class="acct-role">Administrateur</div>
          </div>
        </div>
      </div>

      <!-- Change password -->
      <div class="acct-section">
        <h4 class="acct-section-title">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
          Changer le mot de passe
        </h4>
        <div class="form-group">
          <input type="password" id="acct-new-password" class="form-input" placeholder="Nouveau mot de passe (min. 6 caractères)" autocomplete="new-password">
        </div>
        <button class="btn" onclick="acctChangePassword()">Mettre à jour</button>
      </div>

      <!-- 2FA / OTP -->
      <div class="acct-section">
        <h4 class="acct-section-title">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
          Authentification à deux facteurs (2FA)
          <span class="conn-badge unknown" id="acct-otp-badge" style="margin-left:8px">
            <span class="b-dot"></span>
            <span id="acct-otp-badge-text">—</span>
          </span>
        </h4>

        <!-- Setup button -->
        <div id="acct-otp-setup" class="hidden">
          <button class="btn btn-primary" onclick="acctSetupOTP()">Activer la 2FA</button>
        </div>

        <!-- QR code step -->
        <div id="acct-otp-qr" class="hidden">
          <p class="form-hint">Scannez ce QR code avec votre application d'authentification (Google Authenticator, Authy, etc.)</p>
          <div id="acct-otp-qr-img" style="margin:16px 0;text-align:center"></div>
          <p class="form-hint">Ou entrez cette clé manuellement : <code id="acct-otp-secret" class="otp-secret"></code></p>
          <div class="form-group" style="margin-top:12px">
            <input type="text" id="acct-otp-verify-code" class="form-input" placeholder="Code OTP à 6 chiffres" maxlength="6" inputmode="numeric">
          </div>
          <button class="btn btn-primary" onclick="acctVerifyOTP()">Vérifier et activer</button>
        </div>

        <!-- Disable step -->
        <div id="acct-otp-disable" class="hidden">
          <p class="form-hint">La 2FA est activée. Pour la désactiver, entrez votre code OTP actuel.</p>
          <div class="form-group" style="margin-top:8px">
            <input type="text" id="acct-otp-disable-code" class="form-input" placeholder="Code OTP à 6 chiffres" maxlength="6" inputmode="numeric">
          </div>
          <button class="btn btn-danger" onclick="acctDisableOTP()">Désactiver la 2FA</button>
        </div>
      </div>

      <!-- Logout -->
      <div class="acct-section" style="border-top:1px solid var(--border);padding-top:16px;margin-top:8px">
        <button class="btn btn-danger full-width" onclick="acctLogout()">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1-2 2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
          Se déconnecter
        </button>
      </div>

    </div>
  </div>
</div>`;
  document.body.insertAdjacentHTML("beforeend", html);
})();

// ---- Account modal ----

function openAccountModal() {
  document.getElementById("account-modal").classList.remove("hidden");
  acctLoadUserInfo();
}

function closeAccountModal() {
  document.getElementById("account-modal").classList.add("hidden");
}

// ---- API helpers (delegate to shared apiFetch from api.js) ----

function _acctGet(url) {
  return apiFetch.get(url);
}

function _acctPost(url, body) {
  return apiFetch.post(url, body);
}

// ---- Load user info ----

async function acctLoadUserInfo() {
  try {
    const info = await _acctGet("/api/auth/user-info");
    document.getElementById("acct-username").textContent = info.username;

    const badge = document.getElementById("acct-otp-badge");
    const badgeText = document.getElementById("acct-otp-badge-text");

    document.getElementById("acct-otp-qr").classList.add("hidden");

    if (info.otp_enabled) {
      badge.className = "conn-badge ok";
      badgeText.textContent = "Activée";
      document.getElementById("acct-otp-setup").classList.add("hidden");
      document.getElementById("acct-otp-disable").classList.remove("hidden");
    } else {
      badge.className = "conn-badge unknown";
      badgeText.textContent = "Désactivée";
      document.getElementById("acct-otp-setup").classList.remove("hidden");
      document.getElementById("acct-otp-disable").classList.add("hidden");
    }
  } catch {}
}

// ---- Change password ----

async function acctChangePassword() {
  const pw = document.getElementById("acct-new-password").value;
  if (pw.length < 6) { showToast("Mot de passe : 6 caractères minimum", "error"); return; }
  try {
    await _acctPost("/api/auth/change-password", { username: "", password: pw });
    showToast("Mot de passe mis à jour", "ok");
    document.getElementById("acct-new-password").value = "";
  } catch (e) {
    showToast("Erreur : " + e.message, "error");
  }
}

// ---- OTP setup ----

async function acctSetupOTP() {
  try {
    const res = await _acctPost("/api/auth/setup-otp", {});
    const qrImg = document.createElement("img");
    qrImg.src = "data:image/png;base64," + res.qr_code.replace(/[^A-Za-z0-9+/=]/g, "");
    qrImg.alt = "QR Code";
    qrImg.style.cssText = "max-width:200px;border-radius:8px;border:2px solid var(--border)";
    const qrContainer = document.getElementById("acct-otp-qr-img");
    qrContainer.innerHTML = "";
    qrContainer.appendChild(qrImg);
    document.getElementById("acct-otp-secret").textContent = res.secret;
    document.getElementById("acct-otp-qr").classList.remove("hidden");
    document.getElementById("acct-otp-setup").classList.add("hidden");
  } catch (e) {
    showToast("Erreur : " + e.message, "error");
  }
}

async function acctVerifyOTP() {
  const code = document.getElementById("acct-otp-verify-code").value.trim();
  if (code.length !== 6) { showToast("Entrez un code à 6 chiffres", "error"); return; }
  try {
    await _acctPost("/api/auth/verify-otp", { code });
    showToast("2FA activée avec succès !", "ok");
    document.getElementById("acct-otp-qr").classList.add("hidden");
    acctLoadUserInfo();
  } catch (e) {
    let msg = "Code invalide";
    try { msg = JSON.parse(e.message).detail; } catch {}
    showToast(msg, "error");
  }
}

async function acctDisableOTP() {
  const code = document.getElementById("acct-otp-disable-code").value.trim();
  if (code.length !== 6) { showToast("Entrez un code à 6 chiffres", "error"); return; }
  try {
    await _acctPost("/api/auth/disable-otp", { code });
    showToast("2FA désactivée", "ok");
    document.getElementById("acct-otp-disable-code").value = "";
    acctLoadUserInfo();
  } catch (e) {
    let msg = "Code invalide";
    try { msg = JSON.parse(e.message).detail; } catch {}
    showToast(msg, "error");
  }
}

// ---- Logout ----

function acctLogout() {
  localStorage.removeItem("dm_token");
  if (typeof API !== "undefined") API.token = "";
  closeAccountModal();
  window.location.reload();
}

// ---- Show/hide account button based on auth state ----

function initAccountButton() {
  const btn = document.getElementById("account-btn");
  if (!btn) return;
  if (localStorage.getItem("dm_token")) {
    btn.classList.remove("hidden");
  } else {
    btn.classList.add("hidden");
  }
}
