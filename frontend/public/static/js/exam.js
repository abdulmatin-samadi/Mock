/* Reading / Listening exam room. Answers are autosaved to the server and graded
   only on the server — this script never sees correct answers. */
(function () {
  "use strict";
  const { api, countdown, readConfig, fmt, roomChrome, t } = window.DreamZone;
  const cfg = readConfig("exam-config");
  const form = document.getElementById("exam-form");
  const saveState = document.getElementById("save-state");
  const submitBtn = document.getElementById("submit-btn");
  let dirty = false;
  let submitting = false;

  // ------------------------------------------------------------- answers
  // Only real form fields — the question palette links also carry data-qid.
  const FIELDS = "input[data-qid], select[data-qid], textarea[data-qid]";

  function collect() {
    const answers = {};
    form.querySelectorAll(FIELDS).forEach((el) => {
      const id = el.getAttribute("data-qid");
      if (el.type === "radio") {
        if (el.checked) answers[id] = el.value;
        else if (!(id in answers)) answers[id] = "";
      } else {
        answers[id] = el.value.trim();
      }
    });
    return answers;
  }

  function prefill() {
    Object.entries(cfg.saved || {}).forEach(([qid, value]) => {
      const radios = form.querySelectorAll(`input[type=radio][data-qid="${qid}"]`);
      if (radios.length) {
        radios.forEach((r) => { r.checked = String(r.value) === String(value); });
        return;
      }
      const el = form.querySelector(`input[data-qid="${qid}"], select[data-qid="${qid}"]`);
      if (!el) return;
      el.value = value;
      if (el.classList.contains("slot-input")) setSlot(qid, value);
    });
  }

  function updatePalette() {
    const answers = collect();
    document.querySelectorAll(".q-palette a").forEach((a) => {
      a.classList.toggle("answered", !!answers[a.getAttribute("data-qid")]);
    });
    const counter = document.getElementById("answered-count");
    if (counter) counter.textContent = Object.values(answers).filter(Boolean).length;
    document.querySelectorAll(".pool").forEach((pool) => {
      const part = pool.closest(".room-part");
      const used = new Set(Array.from(part.querySelectorAll(".slot-input")).map((i) => i.value).filter(Boolean));
      pool.querySelectorAll(".pool-item").forEach((b) => b.classList.toggle("used", used.has(b.dataset.label)));
    });
  }

  function changed() {
    dirty = true;
    saveState.textContent = t("Unsaved changes");
    updatePalette();
  }

  async function save(keepalive) {
    if (!dirty || submitting) return;
    dirty = false;
    saveState.textContent = t("Saving…");
    try {
      await api(cfg.answersUrl, { method: "PATCH", json: { answers: collect() }, keepalive: !!keepalive });
      saveState.textContent = t("All answers saved");
    } catch (e) {
      dirty = true;
      saveState.textContent = e.status === 400 ? e.message : t("Offline — will retry");
    }
  }

  async function submit(auto) {
    if (submitting) return;
    submitting = true;
    submitBtn.disabled = true;
    submitBtn.textContent = t("Submitting…");
    try {
      await api(cfg.submitUrl, { method: "POST", json: { answers: collect() } });
      window.location.href = cfg.resultUrl;
    } catch (e) {
      if (e.status === 400 && /already/i.test(e.message)) { window.location.href = cfg.resultUrl; return; }
      submitting = false;
      submitBtn.disabled = false;
      submitBtn.textContent = t("✓ Submit Test");
      alert(t("Could not submit:") + " " + e.message);
    }
  }

  // ------------------------------------------------- drag & drop matching
  let picked = null; // tap-to-select fallback
  function setSlot(qid, label) {
    const slot = form.querySelector(`[data-slot-for="${qid}"]`);
    const input = form.querySelector(`.slot-input[data-qid="${qid}"]`);
    if (!slot || !input) return;
    input.value = label || "";
    const item = label ? slot.closest(".room-part").querySelector(`.pool-item[data-label="${label}"]`) : null;
    slot.querySelector(".slot-value").textContent = label ? `${label}. ${item ? item.dataset.text : ""} ✕` : "";
    slot.classList.toggle("filled", !!label);
  }
  form.addEventListener("dragstart", (e) => {
    const item = e.target.closest(".pool-item");
    if (item) e.dataTransfer.setData("text/plain", item.dataset.label);
  });
  form.addEventListener("dragover", (e) => { if (e.target.closest(".slot")) { e.preventDefault(); e.target.closest(".slot").classList.add("over"); } });
  form.addEventListener("dragleave", (e) => { const s = e.target.closest(".slot"); if (s) s.classList.remove("over"); });
  form.addEventListener("drop", (e) => {
    const slot = e.target.closest(".slot");
    if (!slot) return;
    e.preventDefault();
    slot.classList.remove("over");
    setSlot(slot.dataset.slotFor, e.dataTransfer.getData("text/plain"));
    changed();
  });
  form.addEventListener("click", (e) => {
    const item = e.target.closest(".pool-item");
    if (item) {
      form.querySelectorAll(".pool-item.picked").forEach((b) => b.classList.remove("picked"));
      picked = picked === item.dataset.label ? null : item.dataset.label;
      if (picked) item.classList.add("picked");
      return;
    }
    const slot = e.target.closest(".slot");
    if (slot) {
      if (picked) {
        setSlot(slot.dataset.slotFor, picked);
        form.querySelectorAll(".pool-item.picked").forEach((b) => b.classList.remove("picked"));
        picked = null;
      } else if (slot.classList.contains("filled")) {
        setSlot(slot.dataset.slotFor, "");
      }
      changed();
    }
  });

  // ------------------------------------------------------------- parts
  const audio = document.getElementById("room-audio");
  // Exam mode (full listening test): each part's recording plays at most twice — once more right after
  // the first time — and when it has finished the next part opens by itself. Counts survive a reload.
  const examMode = !!(audio && cfg.examMode);
  const MAX_PLAYS = 2;
  const playsKey = "dz-plays-" + cfg.attemptId;
  let plays = {};
  try { plays = JSON.parse(localStorage.getItem(playsKey) || "{}"); } catch (e) { plays = {}; }
  let audioPart = null; // part whose recording is loaded
  function playsLeft(id) { return MAX_PLAYS - (plays[id] || 0); }
  function showPlays() {
    const badge = document.getElementById("rp-plays");
    if (!examMode || !badge) return;
    const used = Math.min(MAX_PLAYS, (plays[audioPart] || 0) + (audio.paused ? 0 : 1));
    badge.hidden = false;
    badge.textContent = playsLeft(audioPart) > 0 ? `${Math.max(used, 1)}/${MAX_PLAYS}` : `${MAX_PLAYS}/${MAX_PLAYS} ✓`;
    const play = document.getElementById("rp-play");
    if (play) play.disabled = playsLeft(audioPart) <= 0;
  }
  function loadPartAudio(id, src) {
    const rate = audio.playbackRate;
    audio.pause(); audio.setAttribute("src", src); audio.load();
    audio.playbackRate = rate;
    audioPart = id;
    if (!examMode || playsLeft(id) > 0) audio.play().catch(() => {}); // starts as soon as the part opens
    showPlays();
  }
  function showPart(id) {
    document.querySelectorAll("[data-part-tab]").forEach((b) => b.classList.toggle("active", b.dataset.partTab === id));
    document.querySelectorAll(".room-part").forEach((p) => { p.hidden = p.dataset.part !== id; });
    if (audio && cfg.audio) {
      const src = cfg.audio[id];
      if (src && audio.getAttribute("src") !== src) loadPartAudio(id, src);
    }
    updateFab(id);
    window.scrollTo(0, 0);
    save();
  }
  // "Submit Test" only on the last part; earlier parts get "Next part".
  const partIds = Array.from(document.querySelectorAll(".room-part")).map((p) => p.dataset.part);
  const nextBtn = document.getElementById("next-part-btn");
  function updateFab(id) {
    const last = partIds.indexOf(id) === partIds.length - 1;
    submitBtn.hidden = !last;
    nextBtn.hidden = last;
  }
  nextBtn.addEventListener("click", () => {
    const i = partIds.indexOf(document.querySelector(".room-part:not([hidden])").dataset.part);
    if (i < partIds.length - 1) showPart(partIds[i + 1]);
  });
  document.querySelectorAll("[data-part-tab]").forEach((b) => b.addEventListener("click", () => showPart(b.dataset.partTab)));
  if (partIds.length) updateFab(document.querySelector(".room-part:not([hidden])").dataset.part);
  document.querySelectorAll(".q-palette a").forEach((a) => {
    a.addEventListener("click", (e) => {
      const part = a.dataset.partId;
      if (document.querySelector(`.room-part[data-part="${part}"]`).hidden) showPart(part);
      const target = document.getElementById("q-" + a.dataset.qid);
      if (target) { e.preventDefault(); target.scrollIntoView({ behavior: "smooth", block: "center" }); }
    });
  });

  // ------------------------------------------------------- audio player
  if (audio) {
    const play = document.getElementById("rp-play"), seek = document.getElementById("rp-seek");
    const cur = document.getElementById("rp-cur"), dur = document.getElementById("rp-dur");
    const vol = document.getElementById("rp-vol"), speed = document.getElementById("rp-speed");
    const speeds = [1, 1.25, 1.5, 0.75];
    play.addEventListener("click", () => (audio.paused ? audio.play() : audio.pause()));
    audio.addEventListener("play", () => { play.textContent = "❚❚"; play.setAttribute("aria-label", "Pause"); });
    audio.addEventListener("pause", () => { play.textContent = "▶"; play.setAttribute("aria-label", "Play"); });
    audio.addEventListener("loadedmetadata", () => { dur.textContent = fmt(audio.duration); seek.value = 0; cur.textContent = "00:00"; });
    audio.addEventListener("timeupdate", () => {
      cur.textContent = fmt(audio.currentTime);
      if (audio.duration) seek.value = (audio.currentTime / audio.duration) * 100;
    });
    seek.addEventListener("input", () => { if (audio.duration) audio.currentTime = (seek.value / 100) * audio.duration; });
    if (examMode) {
      seek.disabled = true; // no skipping back or forward, as in the real exam
      play.addEventListener("click", (e) => { if (playsLeft(audioPart) <= 0) { e.stopImmediatePropagation(); audio.pause(); } }, true);
      audio.addEventListener("play", showPlays);
      audio.addEventListener("ended", () => {
        const id = audioPart;
        plays[id] = (plays[id] || 0) + 1;
        try { localStorage.setItem(playsKey, JSON.stringify(plays)); } catch (e) { /* private mode */ }
        if (playsLeft(id) > 0) {
          audio.currentTime = 0;
          audio.play().catch(() => {}); // second listening
        } else {
          showPlays();
          const i = partIds.indexOf(id);
          if (i > -1 && i < partIds.length - 1) showPart(partIds[i + 1]);
        }
      });
    }
    // load the recording of the part that is open when the room starts, and play it right away
    // (some browsers allow playing only after the first click — then ▶ starts it)
    const firstPart = document.querySelector(".room-part:not([hidden])");
    const firstSrc = firstPart && cfg.audio ? cfg.audio[firstPart.dataset.part] : "";
    if (firstSrc && !audio.getAttribute("src")) loadPartAudio(firstPart.dataset.part, firstSrc);
    vol.addEventListener("input", () => { audio.volume = Number(vol.value); });
    speed.addEventListener("click", () => {
      const next = speeds[(speeds.indexOf(audio.playbackRate) + 1) % speeds.length];
      audio.playbackRate = next;
      speed.textContent = next + "x";
    });
  }

  // ------------------------------------------------- search in the text
  const searchBox = document.getElementById("room-search");
  const searchInput = document.getElementById("room-search-input");
  const searchCount = document.getElementById("room-search-count");
  function clearMarks() {
    document.querySelectorAll("mark.hl").forEach((m) => m.replaceWith(document.createTextNode(m.textContent)));
    document.querySelectorAll("[data-searchable]").forEach((el) => el.normalize());
  }
  function runSearch() {
    clearMarks();
    const term = (searchInput.value || "").trim();
    let count = 0;
    if (term.length >= 2) {
      const re = new RegExp(term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
      document.querySelectorAll(".room-part:not([hidden]) [data-searchable]").forEach((el) => {
        const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
        const nodes = [];
        while (walker.nextNode()) nodes.push(walker.currentNode);
        nodes.forEach((node) => {
          const text = node.nodeValue;
          if (!re.test(text)) return;
          re.lastIndex = 0;
          const frag = document.createDocumentFragment();
          let last = 0, m;
          while ((m = re.exec(text))) {
            frag.appendChild(document.createTextNode(text.slice(last, m.index)));
            const mark = document.createElement("mark");
            mark.className = "hl";
            mark.textContent = m[0];
            frag.appendChild(mark);
            last = m.index + m[0].length;
            count += 1;
          }
          frag.appendChild(document.createTextNode(text.slice(last)));
          node.replaceWith(frag);
        });
      });
      const first = document.querySelector("mark.hl");
      if (first) first.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    if (searchCount) searchCount.textContent = count;
  }
  const searchBtn = document.getElementById("room-search-btn");
  if (searchBtn) {
    searchBtn.addEventListener("click", () => { searchBox.hidden = !searchBox.hidden; if (!searchBox.hidden) searchInput.focus(); });
    searchInput.addEventListener("input", runSearch);
    document.getElementById("room-search-close").addEventListener("click", () => { searchBox.hidden = true; searchInput.value = ""; runSearch(); });
  }

  // ----------------------------------------------------- resizable panes
  document.querySelectorAll(".divider").forEach((div) => {
    div.addEventListener("pointerdown", (e) => {
      const split = div.parentElement;
      const rect = split.getBoundingClientRect();
      div.setPointerCapture(e.pointerId);
      const move = (ev) => {
        const pct = Math.min(75, Math.max(25, ((ev.clientX - rect.left) / rect.width) * 100));
        split.style.gridTemplateColumns = `${pct}% 10px minmax(0, 1fr)`;
      };
      const up = () => { div.removeEventListener("pointermove", move); div.removeEventListener("pointerup", up); };
      div.addEventListener("pointermove", move);
      div.addEventListener("pointerup", up);
    });
  });

  // -------------------------------------------------- map: enlarge / pen
  const enlarge = document.getElementById("enlarge-modal");
  document.querySelectorAll(".map-card").forEach((card) => {
    const img = card.querySelector("img"), canvas = card.querySelector("canvas");
    const ctx = canvas.getContext("2d");
    let pen = false, drawing = false;
    const fit = () => {
      const data = canvas.width ? ctx.getImageData(0, 0, canvas.width, canvas.height) : null;
      canvas.width = img.clientWidth; canvas.height = img.clientHeight;
      if (data) ctx.putImageData(data, 0, 0);
    };
    img.complete ? fit() : img.addEventListener("load", fit);
    window.addEventListener("resize", fit);
    const pos = (e) => { const r = canvas.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
    canvas.addEventListener("pointerdown", (e) => { if (!pen) return; drawing = true; ctx.beginPath(); ctx.moveTo(...pos(e)); });
    canvas.addEventListener("pointermove", (e) => {
      if (!drawing) return;
      ctx.lineTo(...pos(e)); ctx.strokeStyle = "#dc2626"; ctx.lineWidth = 3; ctx.lineCap = "round"; ctx.stroke();
    });
    ["pointerup", "pointerleave"].forEach((ev) => canvas.addEventListener(ev, () => { drawing = false; }));
    card.querySelector("[data-pen]").addEventListener("click", (e) => {
      pen = !pen; canvas.classList.toggle("active", pen); e.currentTarget.classList.toggle("on", pen);
    });
    card.querySelector("[data-clear]").addEventListener("click", () => ctx.clearRect(0, 0, canvas.width, canvas.height));
    card.querySelector("[data-enlarge]").addEventListener("click", () => {
      enlarge.querySelector("img").src = img.src; enlarge.hidden = false;
    });
  });
  if (enlarge) enlarge.addEventListener("click", (e) => { if (e.target === enlarge || e.target.closest("[data-close-enlarge]")) enlarge.hidden = true; });

  // --------------------------------------------------------------- wiring
  form.addEventListener("input", changed);
  form.addEventListener("change", changed);
  form.addEventListener("submit", (e) => { e.preventDefault(); submit(false); });
  submitBtn.addEventListener("click", (e) => { e.preventDefault(); submit(false); });
  window.addEventListener("beforeunload", () => { if (dirty && !submitting) save(true); });

  roomChrome({ onLeave: () => save(true), isBusy: () => submitting });
  prefill();
  updatePalette();
  setInterval(save, 15000);
  countdown(document.getElementById("timer"), cfg.deadline, cfg.serverNow, () => {
    saveState.textContent = t("Time is up — submitting…");
    submit(true);
  });
})();
