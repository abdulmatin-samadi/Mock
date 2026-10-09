/* Speaking exam room: preparation timer → MediaRecorder recording → replay →
   upload. Each answer is uploaded immediately; the server transcribes and
   evaluates it in the background. */
(function () {
  "use strict";
  const { api, fmt, readConfig, countdown, roomChrome } = window.DreamZone;
  const cfg = readConfig("exam-config");
  const $ = (id) => document.getElementById(id);
  const ui = {
    intro: $("sp-intro"), stage: $("sp-stage"), finish: $("sp-finish"), unsupported: $("sp-unsupported"),
    partLabel: $("sp-part"), qText: $("sp-question"), cue: $("sp-cue"), cueList: $("sp-cue-list"),
    phase: $("sp-phase"), clock: $("sp-clock"), meter: $("sp-meter"), status: $("sp-status"),
    btnMic: $("btn-mic"), btnSkip: $("btn-skip"), btnStop: $("btn-stop"), btnRedo: $("btn-redo"),
    btnUpload: $("btn-upload"), btnFinish: $("btn-finish"), playback: $("sp-playback"), steps: $("sp-steps"),
    counter: $("sp-counter"),
  };

  const questions = cfg.questions || [];
  let index = questions.findIndex((q) => !q.done);
  let stream = null, recorder = null, chunks = [], blob = null, mime = "";
  let timer = null, recordStart = 0, duration = 0, analyser = null, rafId = null;

  if (!window.MediaRecorder || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    ui.intro.hidden = true;
    ui.unsupported.hidden = false;
    return;
  }

  function pickMime() {
    const types = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
    return types.find((t) => MediaRecorder.isTypeSupported(t)) || "";
  }
  function extFor(type) {
    if (type.includes("mp4")) return "m4a";
    if (type.includes("ogg")) return "ogg";
    return "webm";
  }

  function renderSteps() {
    ui.steps.innerHTML = "";
    questions.forEach((q, i) => {
      const s = document.createElement("span");
      s.textContent = i + 1;
      s.title = `${q.partLabel}`;
      if (q.done) s.className = "done";
      else if (i === index) s.className = "current";
      ui.steps.appendChild(s);
    });
    const done = questions.filter((q) => q.done).length;
    ui.counter.textContent = `${done} / ${questions.length} answered`;
  }

  function show(el) { [ui.intro, ui.stage, ui.finish].forEach((x) => { x.hidden = x !== el; }); }
  function setButtons(visible) {
    ["btnSkip", "btnStop", "btnRedo", "btnUpload"].forEach((b) => { ui[b].hidden = !visible.includes(b); });
  }
  function clearTimer() { if (timer) clearInterval(timer); timer = null; }

  function startMeter() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const src = ctx.createMediaStreamSource(stream);
      analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      src.connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);
      const loop = () => {
        analyser.getByteTimeDomainData(data);
        let peak = 0;
        for (const v of data) peak = Math.max(peak, Math.abs(v - 128));
        ui.meter.style.width = Math.min(100, peak * 1.6) + "%";
        rafId = requestAnimationFrame(loop);
      };
      loop();
    } catch (e) { /* meter is optional */ }
  }

  async function enableMic() {
    ui.status.textContent = "";
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      mime = pickMime();
      startMeter();
      next();
    } catch (e) {
      $("sp-status-intro").textContent = "Microphone permission was denied. Allow microphone access in your browser and try again.";
    }
  }

  function next() {
    index = questions.findIndex((q) => !q.done);
    renderSteps();
    if (index === -1) { show(ui.finish); return; }
    const q = questions[index];
    show(ui.stage);
    ui.partLabel.textContent = q.partLabel;
    ui.qText.textContent = q.text;
    ui.cueList.innerHTML = "";
    (q.cue || []).forEach((p) => { const li = document.createElement("li"); li.textContent = p; ui.cueList.appendChild(li); });
    ui.cue.hidden = !(q.cue && q.cue.length);
    const img = $("sp-image");
    img.hidden = !q.image;
    if (q.image) img.src = q.image;
    const args = $("sp-args");
    args.hidden = !q.arguments;
    ["for", "against"].forEach((side) => {
      const list = $("sp-" + side);
      list.innerHTML = "";
      ((q.arguments || {})[side] || []).forEach((t) => { const li = document.createElement("li"); li.textContent = t; list.appendChild(li); });
    });
    ui.playback.hidden = true;
    ui.status.textContent = "";
    prepare(q);
  }

  function prepare(q) {
    clearTimer();
    let left = q.prep;
    ui.phase.textContent = "Preparation time";
    ui.clock.textContent = fmt(left);
    setButtons(["btnSkip"]);
    if (left <= 0) { record(q); return; }
    timer = setInterval(() => {
      left -= 1;
      ui.clock.textContent = fmt(left);
      if (left <= 0) record(q);
    }, 1000);
  }

  function record(q) {
    clearTimer();
    chunks = [];
    blob = null;
    try {
      recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
    } catch (e) {
      recorder = new MediaRecorder(stream);
    }
    mime = recorder.mimeType || mime || "audio/webm";
    recorder.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
    recorder.onstop = () => {
      duration = (Date.now() - recordStart) / 1000;
      blob = new Blob(chunks, { type: mime });
      ui.playback.src = URL.createObjectURL(blob);
      ui.playback.hidden = false;
      ui.phase.textContent = "Review your answer";
      ui.clock.textContent = fmt(duration);
      setButtons(["btnRedo", "btnUpload"]);
    };
    recorder.start(1000);
    recordStart = Date.now();
    let left = q.speak;
    ui.phase.innerHTML = '<span class="rec-dot"></span>Recording — speak now';
    ui.clock.textContent = fmt(left);
    setButtons(["btnStop"]);
    timer = setInterval(() => {
      left -= 1;
      ui.clock.textContent = fmt(left);
      if (left <= 0) stop();
    }, 1000);
  }

  function stop() {
    clearTimer();
    if (recorder && recorder.state !== "inactive") recorder.stop();
  }

  async function upload() {
    if (!blob || blob.size < 1000) {
      ui.status.textContent = "The recording is empty. Please record again.";
      return;
    }
    const q = questions[index];
    const fd = new FormData();
    fd.append("attempt", cfg.attemptId);
    fd.append("question", q.id);
    fd.append("duration", duration.toFixed(1));
    fd.append("audio_file", blob, `answer.${extFor(mime)}`);
    ui.btnUpload.disabled = true;
    ui.btnRedo.disabled = true;
    ui.status.textContent = "Uploading…";
    try {
      await api(cfg.uploadUrl, { method: "POST", formData: fd });
      q.done = true;
      ui.status.textContent = "Saved. The AI is transcribing and evaluating it in the background.";
      setTimeout(next, 700);
    } catch (e) {
      ui.status.textContent = "Upload failed: " + e.message;
      if (/already submitted/i.test(e.message)) { q.done = true; setTimeout(next, 900); }
    } finally {
      ui.btnUpload.disabled = false;
      ui.btnRedo.disabled = false;
    }
  }

  async function finish() {
    ui.btnFinish.disabled = true;
    ui.btnFinish.textContent = "Finishing…";
    try {
      await api(cfg.submitUrl, { method: "POST", json: {} });
      window.location.href = cfg.resultUrl;
    } catch (e) {
      if (/already/i.test(e.message)) { window.location.href = cfg.resultUrl; return; }
      ui.btnFinish.disabled = false;
      ui.btnFinish.textContent = "Finish test";
      alert(e.message);
    }
  }

  ui.btnMic.addEventListener("click", enableMic);
  ui.btnSkip.addEventListener("click", () => record(questions[index]));
  ui.btnStop.addEventListener("click", stop);
  ui.btnRedo.addEventListener("click", () => record(questions[index]));
  ui.btnUpload.addEventListener("click", upload);
  ui.btnFinish.addEventListener("click", finish);
  const early = document.getElementById("btn-finish-early");
  if (early) early.addEventListener("click", () => {
    if (questions.some((q) => q.done)) finish();
  });
  window.addEventListener("beforeunload", (e) => {
    if (recorder && recorder.state === "recording") { e.preventDefault(); e.returnValue = ""; }
  });
  roomChrome({ onLeave: () => { if (recorder && recorder.state === "recording") stop(); } });
  renderSteps();
  if (index === -1) show(ui.finish);
  countdown(document.getElementById("timer"), cfg.deadline, cfg.serverNow, () => {
    if (recorder && recorder.state === "recording") stop();
    ui.status.textContent = "Time is up. Submit any recorded answer, then finish the test.";
  });
})();
