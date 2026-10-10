/* Shared helpers: navigation, CSRF-aware fetch, countdown timers. */
(function () {
  "use strict";

  function getCookie(name) {
    const m = document.cookie.match(new RegExp("(^|;\\s*)" + name + "=([^;]*)"));
    return m ? decodeURIComponent(m[2]) : null;
  }

  /** fetch() wrapper: JSON in/out, session auth + CSRF header. */
  async function api(url, { method = "GET", json, formData, keepalive = false } = {}) {
    const headers = { "X-CSRFToken": getCookie("csrftoken") || "", Accept: "application/json" };
    let body;
    if (json !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(json);
    } else if (formData) {
      body = formData;
    }
    const res = await fetch(url, { method, headers, body, credentials: "same-origin", keepalive });
    let data = null;
    try { data = await res.json(); } catch (e) { /* empty body */ }
    if (!res.ok) {
      const err = new Error(errorText(data) || `Request failed (${res.status})`);
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  function errorText(data) {
    if (!data) return "";
    if (typeof data === "string") return data;
    if (Array.isArray(data)) return data.join(" ");
    if (data.detail) return data.detail;
    return Object.values(data).flat().join(" ");
  }

  function fmt(sec) {
    sec = Math.max(0, Math.floor(sec));
    const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
    const mm = String(m).padStart(2, "0"), ss = String(s).padStart(2, "0");
    return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
  }

  /** Countdown to a server deadline, corrected for client clock skew. */
  function countdown(el, deadlineIso, serverNowIso, onEnd) {
    if (!el || !deadlineIso) return null;
    const skew = serverNowIso ? new Date(serverNowIso).getTime() - Date.now() : 0;
    const end = new Date(deadlineIso).getTime();
    let fired = false;
    function tick() {
      const left = (end - (Date.now() + skew)) / 1000;
      el.textContent = fmt(left);
      el.classList.toggle("warn", left <= 300 && left > 60);
      el.classList.toggle("danger", left <= 60);
      if (left <= 0 && !fired) {
        fired = true;
        clearInterval(timer);
        onEnd && onEnd();
      }
    }
    const timer = setInterval(tick, 500);
    tick();
    return timer;
  }

  function readConfig(id) {
    const el = document.getElementById(id);
    return el ? JSON.parse(el.textContent) : {};
  }

  document.addEventListener("click", function (e) {
    const toggle = e.target.closest("[data-toggle]");
    if (toggle) {
      const target = document.querySelector(toggle.getAttribute("data-toggle"));
      if (target) {
        target.classList.toggle("open");
        toggle.setAttribute("aria-expanded", target.classList.contains("open"));
      }
      return;
    }
    const dd = e.target.closest(".dropdown > button");
    document.querySelectorAll(".dropdown.open").forEach((d) => { if (!dd || d !== dd.parentElement) d.classList.remove("open"); });
    if (dd) dd.parentElement.classList.toggle("open");
    const sidebar = document.querySelector(".sidebar.open");
    if (sidebar && !e.target.closest(".sidebar") && !e.target.closest(".sidebar-toggle")) sidebar.classList.remove("open");
  });

  document.addEventListener("submit", function (e) {
    const msg = e.target.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  /** Shared exam-room controls: back button + exit dialog, full screen, text size. */
  function roomChrome({ onLeave, isBusy } = {}) {
    const modal = document.getElementById("exit-modal");
    const back = document.getElementById("room-back");
    if (modal && back) {
      const close = () => { modal.hidden = true; back.focus(); };
      back.addEventListener("click", () => { modal.hidden = false; document.getElementById("exit-stay").focus(); });
      document.getElementById("exit-stay").addEventListener("click", close);
      modal.addEventListener("click", (e) => { if (e.target === modal) close(); });
      document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !modal.hidden) close(); });
      document.getElementById("exit-leave").addEventListener("click", async (e) => {
        e.preventDefault();
        const href = e.currentTarget.href;
        if (isBusy && isBusy()) return;
        try { if (onLeave) await onLeave(); } catch (err) { /* answers are autosaved anyway */ }
        window.location.href = href;
      });
    }
    const fs = document.getElementById("room-fullscreen");
    if (fs) {
      fs.addEventListener("click", () => {
        if (document.fullscreenElement) document.exitFullscreen();
        else if (document.documentElement.requestFullscreen) document.documentElement.requestFullscreen();
      });
    }
    const font = document.getElementById("font-btn");
    if (font) {
      const sizes = ["", "font-lg", "font-xl"];
      let i = 0;
      try { i = Math.max(0, sizes.indexOf(localStorage.getItem("bw-font") || "")); } catch (e) { /* no storage */ }
      const apply = () => { sizes.forEach((c) => c && document.body.classList.remove(c)); if (sizes[i]) document.body.classList.add(sizes[i]); };
      apply();
      font.addEventListener("click", () => {
        i = (i + 1) % sizes.length;
        apply();
        try { localStorage.setItem("bw-font", sizes[i]); } catch (e) { /* no storage */ }
      });
    }
  }

  // Dark / light theme: one button flips it; the choice is remembered in this browser.
  document.querySelectorAll("[data-theme-toggle]").forEach((btn) => btn.addEventListener("click", () => {
    const dark = document.documentElement.getAttribute("data-theme") !== "dark";
    if (dark) document.documentElement.setAttribute("data-theme", "dark");
    else document.documentElement.removeAttribute("data-theme");
    try { localStorage.setItem("dz-theme", dark ? "dark" : "light"); } catch (e) { /* private mode */ }
  }));

  // Texts translated on the server ({% js_i18n %}); falls back to the English text.
  let texts = {};
  try { texts = JSON.parse((document.getElementById("dz-i18n") || {}).textContent || "{}"); } catch (e) { texts = {}; }
  const t = (s) => texts[s] || s;

  window.DreamZone = { api, fmt, countdown, readConfig, getCookie, roomChrome, t };
})();
