/* Writing exam room: live word count, local draft backup, server submission. */
(function () {
  "use strict";
  const { api, countdown, readConfig, roomChrome } = window.DreamZone;
  const cfg = readConfig("exam-config");
  const WORD_RE = /[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*/g;
  const submitBtn = document.getElementById("submit-btn");
  const saveState = document.getElementById("save-state");
  let submitting = false;

  const key = (taskId) => `bw-draft-${cfg.attemptId}-${taskId}`;
  const count = (text) => (text.match(WORD_RE) || []).length;
  const areas = Array.from(document.querySelectorAll("textarea[data-task]"));

  function store(fn) { try { fn(); } catch (e) { /* storage unavailable */ } }

  function refresh(area) {
    const id = area.getAttribute("data-task");
    const min = Number(area.getAttribute("data-min") || 0);
    const max = Number(area.getAttribute("data-max") || 0);
    const n = count(area.value);
    const el = document.querySelector(`[data-count-for="${id}"]`);
    if (el) {
      const target = min ? ` · target ${min}${max ? "–" + max : "+"}` : "";
      el.textContent = `${n} word${n === 1 ? "" : "s"}${target}`;
      el.classList.toggle("under", !!min && n < min);
      el.classList.toggle("met", !!min && n >= min && (!max || n <= max));
      el.classList.toggle("over", !!max && n > max);
    }
  }

  let dirty = false;
  async function saveDrafts(keepalive) {
    if (!dirty || submitting || !cfg.draftsUrl) return;
    dirty = false;
    const drafts = {};
    areas.forEach((a) => { drafts[a.getAttribute("data-task")] = a.value; });
    try {
      await api(cfg.draftsUrl, { method: "PATCH", json: { drafts }, keepalive: !!keepalive });
      saveState.textContent = "Draft saved";
    } catch (e) {
      dirty = true;
      saveState.textContent = "Draft kept on this device — will retry";
    }
  }

  areas.forEach((area) => {
    const id = area.getAttribute("data-task");
    const server = (cfg.drafts || {})[id] || "";
    let local = "";
    store(() => { local = localStorage.getItem(key(id)) || ""; });
    // Prefer the longer draft (this device may be ahead of the server, or vice versa).
    if (!area.value) area.value = local.length > server.length ? local : server;
    refresh(area);
    area.addEventListener("input", () => {
      refresh(area);
      store(() => localStorage.setItem(key(area.getAttribute("data-task")), area.value));
      dirty = true;
      saveState.textContent = "Unsaved changes";
    });
    area.addEventListener("paste", () => { saveState.textContent = "Pasted text — make sure it is your own work"; });
  });

  document.querySelectorAll("[data-task-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-task-tab");
      document.querySelectorAll("[data-task-tab]").forEach((b) => b.classList.toggle("active", b === btn));
      document.querySelectorAll("[data-task-panel]").forEach((p) => { p.hidden = p.getAttribute("data-task-panel") !== id; });
    });
  });

  async function submit(auto) {
    if (submitting) return;
    const essays = {};
    areas.forEach((a) => { essays[a.getAttribute("data-task")] = a.value; });
    submitting = true;
    submitBtn.disabled = true;
    submitBtn.textContent = "Submitting…";
    try {
      await api(cfg.submitUrl, { method: "POST", json: { essays } });
      areas.forEach((a) => store(() => localStorage.removeItem(key(a.getAttribute("data-task")))));
      window.location.href = cfg.resultUrl;
    } catch (e) {
      if (e.status === 400 && /already/i.test(e.message)) { window.location.href = cfg.resultUrl; return; }
      submitting = false;
      submitBtn.disabled = false;
      submitBtn.textContent = "Submit for evaluation";
      alert("Could not submit: " + e.message);
    }
  }

  submitBtn.addEventListener("click", (e) => { e.preventDefault(); submit(false); });
  setInterval(saveDrafts, 10000);
  roomChrome({ onLeave: () => saveDrafts(true), isBusy: () => submitting });
  window.addEventListener("beforeunload", () => { if (dirty && !submitting) saveDrafts(true); });
  countdown(document.getElementById("timer"), cfg.deadline, cfg.serverNow, () => {
    saveState.textContent = "Time is up — submitting…";
    if (areas.some((a) => a.value.trim())) submit(true);
  });
})();
