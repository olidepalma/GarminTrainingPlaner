import { api, $, table, sports, fmt, toast } from "./core.js";
let reviewState = null,
  feedbackDirty = false;
async function loadReview() {
  if (feedbackDirty) return;
  reviewState = await api("/api/coach/review");
  $("coach-review-dates").textContent =
    reviewState.from + " — " + reviewState.through;
  table(
    "coach-review-table",
    Object.entries(reviewState.sports).map(([sport, r]) => [
      sports[sport] || sport,
      r.planned.sessions + " sesiones · " + fmt(r.planned.minutes, 0) + " min",
      r.actual.sessions + " sesiones · " + fmt(r.actual.minutes, 0) + " min",
      fmt(r.actual.km) + " km",
      r.volume_change_percent == null
        ? "Sin base suficiente"
        : fmt(r.volume_change_percent) +
          " % · " +
          r.prior_active_weeks +
          " semanas con registros",
    ]),
  );
  $("coach-review-limitations").textContent = reviewState.limitations;
  $("coach-fatigue").value = reviewState.feedback?.fatigue ?? "";
  $("coach-effort").value = reviewState.feedback?.effort ?? "";
  $("coach-feedback").value = reviewState.feedback?.notes || "";
}
function init() {
  $("coach-feedback-form").addEventListener("input", () => {
    feedbackDirty = true;
  });
  $("coach-feedback-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.submitter;
    button.disabled = true;
    try {
      await api("/api/coach/feedback", {
        week_start: reviewState.from,
        fatigue: $("coach-fatigue").value
          ? Number($("coach-fatigue").value)
          : null,
        effort: $("coach-effort").value
          ? Number($("coach-effort").value)
          : null,
        notes: $("coach-feedback").value,
      });
      feedbackDirty = false;
      toast("Revisión guardada para la próxima planificación.");
    } catch (error) {
      toast(error.message, true);
    } finally {
      button.disabled = false;
    }
  });
}

export { init, reviewState, feedbackDirty, loadReview };
