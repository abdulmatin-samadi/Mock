/* Mistakes notebook (retry, reveal, learned) and the "Why?" AI explanation, also used on result pages. */
(function () {
  "use strict";
  const { api, t } = window.DreamZone;
  const list = document.querySelector("[data-explain-lang]");
  let lang = list ? list.dataset.explainLang : "";

  function post(url, fields) {
    const fd = new FormData();
    Object.entries(fields || {}).forEach(([k, v]) => fd.append(k, v));
    return api(url, { method: "POST", formData: fd });
  }

  document.querySelectorAll(".mk-lang [data-lang]").forEach((b) => b.addEventListener("click", () => {
    lang = b.dataset.lang;
    document.querySelectorAll(".mk-lang [data-lang]").forEach((x) => x.classList.toggle("active", x === b));
    document.querySelectorAll(".mk-explain").forEach((box) => { box.hidden = true; box.dataset.lang = ""; });
  }));

  async function explain(card, box, button) {
    if (!box.hidden && box.dataset.lang === lang) { box.hidden = true; return; }
    box.hidden = false;
    box.className = box.className.replace(/\s?is-\w+/g, "") + " is-loading";
    box.textContent = t("✨ AI is writing an explanation…");
    button.disabled = true;
    try {
      const data = await post(card.dataset.explainUrl, { lang: lang });
      box.className = box.className.replace(/\s?is-\w+/g, "");
      box.textContent = "";
      const tag = document.createElement("b");
      tag.textContent = data.source === "teacher" ? t("Teacher's note") : t("✨ AI explanation");
      const p = document.createElement("p");
      p.textContent = data.text;
      box.append(tag, p);
      box.dataset.lang = lang;
    } catch (e) {
      box.className = box.className.replace(/\s?is-\w+/g, "") + " is-error";
      box.textContent = e.message;
    } finally {
      button.disabled = false;
    }
  }

  // "Why?" buttons on result pages: <tr data-explain-url> … <button data-why> … <div class="mk-explain">
  document.querySelectorAll("[data-explain-url]").forEach((card) => {
    const why = card.querySelector("[data-why]");
    const box = card.querySelector(".mk-explain");
    if (why && box) why.addEventListener("click", () => explain(card, box, why));
  });

  document.querySelectorAll(".mk-card").forEach((card) => {
    const form = card.querySelector(".mk-try");
    const out = card.querySelector(".mk-out");
    const show = (ok, answer) => {
      out.hidden = false;
      out.className = "mk-out " + (ok === null ? "is-info" : ok ? "is-good" : "is-bad");
      out.textContent = ok === null ? `${t("Answer")}: ${answer}`
        : ok ? `✓ ${t("Correct!")} ${answer}` : `✗ ${t("Not quite — try again.")}`;
      if (ok) card.classList.add("solved");
    };
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const field = form.querySelector("[name=answer]:checked") || form.querySelector("input.mk-input");
      const value = field ? field.value.trim() : "";
      if (!value) { form.querySelector("[name=answer]").focus(); return; }
      try {
        const data = await post(card.dataset.checkUrl, { answer: value });
        show(data.correct, data.correct ? data.answer : "");
      } catch (err) { out.hidden = false; out.className = "mk-out is-bad"; out.textContent = err.message; }
    });
    card.querySelector("[data-reveal]").addEventListener("click", async () => {
      try { const data = await post(card.dataset.checkUrl, { answer: "" }); show(null, data.answer); } catch (e) { /* ignore */ }
    });
    card.querySelector("[data-learned]").addEventListener("click", async () => {
      try {
        await post(card.dataset.learnedUrl, {});
        card.classList.add("gone");
        setTimeout(() => card.remove(), 350);
      } catch (e) { /* ignore */ }
    });
  });
})();
