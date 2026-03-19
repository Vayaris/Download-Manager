// ============================================================
//  Download Manager — Shared API helpers
//  Loaded before app.js / settings.js / account.js
// ============================================================

// ---- HTML escaping ----

function escHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// ---- Formatters ----

function formatSize(bytes) {
  if (!bytes || bytes === 0) return "\u2014";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

function formatSpeed(bps) {
  if (!bps || bps === 0) return "\u2014";
  return formatSize(bps) + "/s";
}

// ---- Auth token helper ----

function getAuthToken() {
  return localStorage.getItem("dm_token") || "";
}

// ---- API fetch helper ----

const apiFetch = {
  token: localStorage.getItem("dm_token") || "",

  _headers() {
    const h = { "Content-Type": "application/json" };
    if (this.token) h["Authorization"] = `Bearer ${this.token}`;
    return h;
  },

  _handleUnauth() {
    // Pages can override this
  },

  async _request(url, opts) {
    const r = await fetch(url, opts);
    if (r.status === 401) {
      this._handleUnauth();
      throw new Error("Unauthorized");
    }
    if (!r.ok) {
      const text = await r.text();
      let msg = text;
      try {
        const json = JSON.parse(text);
        if (typeof json.detail === "string") {
          msg = json.detail;
        } else if (Array.isArray(json.detail)) {
          // Pydantic validation errors
          msg = json.detail.map(e => e.msg || e.message || JSON.stringify(e)).join(", ");
        }
      } catch {}
      // Truncate very long messages (e.g. magnet URIs echoed back)
      if (msg.length > 200) msg = msg.slice(0, 197) + "…";
      throw new Error(msg);
    }
    return r.json();
  },

  async get(url) {
    return this._request(url, { headers: this._headers() });
  },

  async post(url, body) {
    return this._request(url, { method: "POST", headers: this._headers(), body: JSON.stringify(body) });
  },

  async put(url, body) {
    return this._request(url, { method: "PUT", headers: this._headers(), body: JSON.stringify(body) });
  },

  async del(url, body) {
    const opts = { method: "DELETE", headers: this._headers() };
    if (body !== undefined) opts.body = JSON.stringify(body);
    return this._request(url, opts);
  },
};
