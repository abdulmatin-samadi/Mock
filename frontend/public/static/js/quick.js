// Quick entry: keep typed text in this browser so it survives an expired form or a closed tab.
(function () {
  const form = document.querySelector("form.qk-form");
  if (!form) return;
  const areas = Array.from(form.querySelectorAll("textarea[name]"));
  const key = "dz-draft:" + location.pathname;
  const MAX_AGE = 3 * 24 * 3600 * 1000;
  const read = () => { try { return JSON.parse(localStorage.getItem(key) || "null"); } catch (e) { return null; } };
  const write = () => {
    const values = {}; areas.forEach((a) => { values[a.name] = a.value; });
    try { localStorage.setItem(key, JSON.stringify({ t: Date.now(), values })); } catch (e) {}
  };
  let timer;
  areas.forEach((a) => a.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(write, 400); }));
  form.addEventListener("submit", write);

  const draft = read();
  if (!draft || !draft.values || Date.now() - draft.t > MAX_AGE) return;
  const differs = areas.some((a) => (draft.values[a.name] || "").trim() && (draft.values[a.name] || "") !== a.value);
  if (!differs) return;
  const mins = Math.max(1, Math.round((Date.now() - draft.t) / 60000));
  const ago = mins < 60 ? mins + " min" : Math.round(mins / 60) + " h";
  const bar = document.createElement("div");
  bar.className = "alert alert-info qk-restore";
  bar.innerHTML = '<span>📝 You have unsaved text from ' + ago + ' ago.</span>' +
    '<span class="row"><button type="button" class="btn btn-sm" data-restore>Restore it</button>' +
    '<button type="button" class="btn btn-sm btn-ghost" data-dismiss>Dismiss</button></span>';
  form.prepend(bar);
  bar.querySelector("[data-restore]").addEventListener("click", () => {
    areas.forEach((a) => { if (draft.values[a.name] !== undefined) a.value = draft.values[a.name]; });
    bar.remove();
  });
  bar.querySelector("[data-dismiss]").addEventListener("click", () => {
    try { localStorage.removeItem(key); } catch (e) {}
    bar.remove();
  });
})();
// After a successful save the mock page receives ?quick_saved=<path>: forget that draft.
(function () {
  const saved = new URLSearchParams(location.search).get("quick_saved");
  if (saved) { try { localStorage.removeItem("dz-draft:" + saved); } catch (e) {} }
})();
