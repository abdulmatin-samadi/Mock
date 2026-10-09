/* Result-status polling: reload the page when the AI evaluation finishes. */
(function () {
  "use strict";
  const { api } = window.DreamZone;
  const poll = document.querySelector("[data-poll-url]");
  if (!poll) return;
  const url = poll.getAttribute("data-poll-url");
  const start = Date.now();
  const timer = setInterval(async () => {
    if (Date.now() - start > 15 * 60 * 1000) { clearInterval(timer); return; }
    try {
      const data = await api(url);
      if (data.status !== "evaluating") { clearInterval(timer); window.location.reload(); }
    } catch (e) { /* keep polling */ }
  }, 4000);
})();
