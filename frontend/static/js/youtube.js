(function() {
  "use strict";
  const state = { id: "", data: null, destination: "", timer: null, status: null };

  function isYouTube(value) {
    try {
      const url = new URL(value);
      const host = url.hostname.toLowerCase().replace(/^www\./, "");
      return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password
        && ["", "80", "443"].includes(url.port)
        && ["youtube.com", "youtu.be", "music.youtube.com", "youtubekids.com"].some(d => host === d || host.endsWith(`.${d}`));
    } catch { return false; }
  }
  function isChannel(value) {
    try { return /^\/(?:@[^/]+|channel\/[^/]+|c\/[^/]+|user\/[^/]+)\/?$/.test(new URL(value).pathname); }
    catch { return false; }
  }
  function hasPlaylist(value) {
    try { const u = new URL(value); return Boolean(u.searchParams.get("list")) || u.pathname === "/playlist"; }
    catch { return false; }
  }

  async function maybeHandle(links, files, destination) {
    if ((files || []).length || links.length !== 1 || !isYouTube(links[0])) return false;
    state.destination = destination;
    await open(links[0]);
    return true;
  }

  async function open(url) {
    close();
    const channel = isChannel(url), playlist = hasPlaylist(url);
    const overlay = document.createElement("div");
    overlay.id = "youtube-analysis-modal";
    overlay.className = "modal-overlay youtube-modal-overlay";
    overlay.innerHTML = `<div class="modal-box youtube-modal" role="dialog" aria-modal="true">
      <div class="youtube-modal-head"><div><span class="youtube-kicker">YouTube</span><h3>${t("youtube_analyze_title")}</h3></div><button class="btn-close" data-youtube-close>×</button></div>
      <div class="youtube-source-url">${escHtml(url)}</div>
      ${channel ? `<div class="youtube-filter"><span>${t("youtube_channel_content")}</span><label><input type="radio" name="youtube-filter" value="videos"> ${t("youtube_videos")}</label><label><input type="radio" name="youtube-filter" value="shorts"> Shorts</label><label><input type="radio" name="youtube-filter" value="both" checked> ${t("youtube_both")}</label></div>` : ""}
      ${playlist && !channel ? `<label class="youtube-playlist-choice"><input id="youtube-expand-playlist" type="checkbox" checked> ${t("youtube_full_playlist")}</label>` : ""}
      <div id="youtube-analysis-state" class="youtube-analysis-state"><span class="spinner"></span>${t("youtube_analysis_running")}</div>
      <div id="youtube-analysis-result" class="hidden"></div>
      <div class="youtube-modal-actions"><button class="btn btn-ghost" data-youtube-close>${t("btn_cancel")}</button></div>
    </div>`;
    document.body.appendChild(overlay);
    overlay.querySelectorAll("[data-youtube-close]").forEach(b => b.addEventListener("click", close));
    overlay.addEventListener("click", e => { if (e.target === overlay) close(); });
    await start(url, channel ? "both" : "videos", true);
    overlay.querySelectorAll("input[name=youtube-filter]").forEach(input => input.addEventListener("change", e => start(url, e.target.value, true)));
    overlay.querySelector("#youtube-expand-playlist")?.addEventListener("change", e => start(url, "videos", e.target.checked));
  }

  async function start(url, filter, expand) {
    clearTimeout(state.timer);
    if (state.id) {
      await API.del(`/api/youtube/analyses/${state.id}`).catch(() => {});
      state.id = "";
    }
    const box = document.getElementById("youtube-analysis-state"), result = document.getElementById("youtube-analysis-result");
    if (!box || !result) return;
    box.className = "youtube-analysis-state";
    box.innerHTML = `<span class="spinner"></span>${t("youtube_analysis_running")}`;
    result.classList.add("hidden");
    try {
      const created = await API.post("/api/youtube/analyses", { url, content_filter: filter, expand_playlist: expand });
      state.id = created.analysis_id;
      poll();
    } catch (error) { box.classList.add("error"); box.textContent = error.message; }
  }

  async function poll() {
    try {
      const data = await API.get(`/api/youtube/analyses/${state.id}`);
      if (data.status === "complete") { state.data = data; await render(data); return; }
      if (["error", "cancelled"].includes(data.status)) {
        const box = document.getElementById("youtube-analysis-state");
        if (box) { box.classList.add("error"); box.textContent = data.error || t("youtube_analysis_failed"); }
        return;
      }
      const box = document.getElementById("youtube-analysis-state");
      if (box) box.innerHTML = `<span class="spinner"></span>${t("youtube_analysis_progress", { n: data.progress || 0 })}`;
      state.timer = setTimeout(poll, 1000);
    } catch (error) {
      const box = document.getElementById("youtube-analysis-state");
      if (box) { box.classList.add("error"); box.textContent = error.message; }
    }
  }

  async function render(data) {
    document.getElementById("youtube-analysis-state")?.classList.add("hidden");
    const result = document.getElementById("youtube-analysis-result");
    result.classList.remove("hidden");
    try { state.status = await API.get("/api/settings/youtube/status"); } catch { state.status = { ready: false }; }
    const directAvailable = Boolean(state.status.ready && state.status.direct_enabled);
    const allDebridAvailable = Boolean(state.status.alldebrid_enabled);
    const defaultEngine = allDebridAvailable ? "alldebrid" : "youtube";
    result.innerHTML = `<div class="youtube-result-head"><div><strong>${escHtml(data.title)}</strong><span>${t("youtube_found", { n: data.count })}</span></div><input id="youtube-search" class="form-input" type="search" placeholder="${t("youtube_search")}"></div>
      <div class="youtube-select-bar"><label><input id="youtube-select-all" type="checkbox"> ${t("youtube_select_all")}</label><span id="youtube-selected-count"></span></div>
      <div id="youtube-items" class="youtube-items"></div>
      <div class="youtube-download-options"><label><span>${t("youtube_engine")}</span><select id="youtube-engine" class="form-input"><option value="alldebrid" ${allDebridAvailable ? "" : "disabled"} ${defaultEngine === "alldebrid" ? "selected" : ""}>AllDebrid${allDebridAvailable ? "" : ` — ${t("youtube_not_configured")}`}</option><option value="youtube" ${directAvailable ? "" : "disabled"} ${defaultEngine === "youtube" ? "selected" : ""}>${t("youtube_direct")}${directAvailable ? "" : ` — ${state.status.ready ? t("youtube_disabled") : t("youtube_not_installed")}`}</option></select></label>
      <label id="youtube-profile-wrap" class="hidden"><span>${t("youtube_profile")}</span><select id="youtube-profile" class="form-input"><option value="mp4">${t("youtube_profile_mp4")}</option><option value="mkv_multi">${t("youtube_profile_mkv")}</option></select></label></div>
      ${directAvailable ? "" : `<a class="youtube-setup-link" href="/settings-page#youtube">${state.status.ready ? t("youtube_enable_hint") : t("youtube_install_hint")}</a>`}
      ${state.status.ready && allDebridAvailable ? `<p class="form-hint">${t("youtube_fallback_hint")}</p>` : ""}
      <div class="youtube-submit-row"><span id="youtube-submit-summary"></span><button id="youtube-submit" class="btn btn-primary">${t("youtube_add_batch")}</button></div>`;
    const items = result.querySelector("#youtube-items");
    items.innerHTML = data.items.map(item => `<label class="youtube-item${item.duplicate ? " duplicate" : ""}" data-search="${escHtml(`${item.title} ${item.channel}`.toLowerCase())}"><input type="checkbox" value="${escHtml(item.id)}" ${item.selected ? "checked" : ""}><span><strong>${escHtml(item.title)}</strong><small>${escHtml(item.channel || "YouTube")} · ${item.kind === "short" ? "Short" : duration(item.duration)}${item.duplicate ? ` · ${t("youtube_duplicate")}` : ""}</small></span><em>${item.kind === "short" ? "SHORT" : "VIDEO"}</em></label>`).join("");
    const refresh = () => {
      const checks = [...items.querySelectorAll("input")], visible = checks.filter(c => !c.closest(".youtube-item").classList.contains("filtered")), selected = checks.filter(c => c.checked);
      result.querySelector("#youtube-selected-count").textContent = t("youtube_selected", { n: selected.length });
      result.querySelector("#youtube-submit-summary").textContent = t("youtube_selected", { n: selected.length });
      result.querySelector("#youtube-submit").disabled = !selected.length || (!allDebridAvailable && !directAvailable);
      const all = result.querySelector("#youtube-select-all");
      all.checked = Boolean(visible.length) && visible.every(c => c.checked);
      all.indeterminate = visible.some(c => c.checked) && !all.checked;
    };
    items.addEventListener("change", refresh);
    result.querySelector("#youtube-select-all").addEventListener("change", e => { items.querySelectorAll(".youtube-item:not(.filtered) input").forEach(c => { c.checked = e.target.checked; }); refresh(); });
    result.querySelector("#youtube-search").addEventListener("input", e => { const q = e.target.value.trim().toLowerCase(); items.querySelectorAll(".youtube-item").forEach(row => row.classList.toggle("filtered", q && !row.dataset.search.includes(q))); refresh(); });
    result.querySelector("#youtube-engine").addEventListener("change", e => result.querySelector("#youtube-profile-wrap").classList.toggle("hidden", e.target.value !== "youtube"));
    result.querySelector("#youtube-profile-wrap").classList.toggle("hidden", defaultEngine !== "youtube");
    result.querySelector("#youtube-submit").addEventListener("click", submit);
    refresh();
  }

  function duration(seconds) {
    if (!seconds) return t("youtube_duration_unknown");
    const minutes = Math.floor(seconds / 60), hours = Math.floor(minutes / 60);
    return `${hours ? `${hours} h ` : ""}${String(minutes % 60).padStart(2, "0")} min`;
  }

  async function submit() {
    const modal = document.getElementById("youtube-analysis-modal"), button = modal.querySelector("#youtube-submit");
    const selected = [...modal.querySelectorAll("#youtube-items input:checked")].map(i => i.value);
    button.disabled = true;
    try {
      const response = await API.post(`/api/youtube/analyses/${state.id}/submit`, { selected_ids: selected, destination: state.destination, engine: modal.querySelector("#youtube-engine").value, output_profile: modal.querySelector("#youtube-profile").value, package_name: state.data.title });
      window.resetUnifiedComposer?.();
      showToast(t("youtube_added", { n: response.added }), "ok");
      close(false);
    } catch (error) { showToast(t("error_prefix") + error.message, "error"); button.disabled = false; }
  }

  function close(cancelRemote = true) {
    clearTimeout(state.timer);
    const id = state.id; state.id = "";
    document.getElementById("youtube-analysis-modal")?.remove();
    if (cancelRemote && id) API.del(`/api/youtube/analyses/${id}`).catch(() => {});
  }
  window.YouTubeUI = { maybeHandle, isYouTube };
})();
