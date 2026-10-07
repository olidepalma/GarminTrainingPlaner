import {
  table,
  day,
  sports,
  hours,
  fmt,
  $,
  api,
  toast,
  action,
} from "./core.js";
let dashboardData = null,
  visibleRows = 30,
  viewVersion = 0;
function activityRows() {
  const rows = dashboardData.activities;
  table(
    "activities",
    rows
      .slice(0, visibleRows)
      .map((a) => [
        a.name,
        day(a.day),
        sports[a.sport] || "Otros",
        hours(a.duration_seconds),
        fmt(a.distance_m / 1000) + " km",
        fmt(a.elevation_m, 0) + " m",
        a.average_hr == null ? "—" : fmt(a.average_hr, 0) + " ppm",
      ]),
  );
  $("activity-count").textContent =
    `${Math.min(visibleRows, rows.length)} de ${rows.length} actividades`;
  $("more").hidden = visibleRows >= rows.length;
}
function drawWeeks(weeks) {
  const ns = "http://www.w3.org/2000/svg",
    svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 720 220");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Horas de entrenamiento por semana");
  const title = document.createElementNS(ns, "title");
  title.textContent = weeks
    .map((w) => `${w.week}: ${fmt(w.hours)} horas`)
    .join(". ");
  svg.append(title);
  const max = Math.max(1, ...weeks.map((w) => w.hours)),
    step = 640 / Math.max(weeks.length, 1);
  weeks.forEach((w, i) => {
    const rect = document.createElementNS(ns, "rect"),
      height = (w.hours / max) * 135;
    Object.entries({
      x: 45 + i * step + step * 0.18,
      y: 170 - height,
      width: step * 0.64,
      height: Math.max(height, 1),
      rx: 4,
      fill: "#89a565",
    }).forEach(([k, v]) => rect.setAttribute(k, String(v)));
    const label = document.createElementNS(ns, "text");
    label.setAttribute("x", String(45 + i * step + step / 2));
    label.setAttribute("y", "197");
    label.setAttribute("text-anchor", "middle");
    label.textContent = day(w.week);
    const total = document.createElementNS(ns, "text");
    total.setAttribute("x", String(45 + i * step + step / 2));
    total.setAttribute("y", String(160 - height));
    total.setAttribute("text-anchor", "middle");
    total.textContent = fmt(w.hours) + " h";
    svg.append(rect, label, total);
  });
  $("week-chart").replaceChildren(svg);
}
async function loadDashboard() {
  const own = ++viewVersion;
  const sport = $("sport").value;
  const data = await api(
    `/api/dashboard?days=${$("days").value}${sport ? "&sport=" + encodeURIComponent(sport) : ""}`,
  );
  if (own !== viewVersion) return;
  dashboardData = data;
  visibleRows = 30;
  $("date-range").textContent =
    `${day(data.from)} — ${day(data.through)} · ${new Date(data.through).getFullYear()}`;
  $("sessions").textContent = fmt(data.totals.sessions, 0);
  $("hours").textContent = fmt(data.totals.hours) + " h";
  $("distance").textContent = fmt(data.totals.distance_km) + " km";
  $("elevation").textContent = fmt(data.totals.elevation_m, 0) + " m";
  $("empty").hidden = data.activities.length > 0;
  drawWeeks(data.weeks);
  $("sport-chart").replaceChildren();
  for (const s of data.sports) {
    const row = document.createElement("div");
    row.className = "sport-row";
    const name = document.createElement("span"),
      amount = document.createElement("span"),
      progress = document.createElement("progress");
    name.textContent = sports[s.sport] || "Otros";
    amount.textContent = `${fmt(s.hours)} h · ${s.sessions} sesiones`;
    progress.max = Math.max(data.totals.hours, 1);
    progress.value = s.hours;
    progress.setAttribute(
      "aria-label",
      name.textContent + " " + amount.textContent,
    );
    row.append(name, amount, progress);
    $("sport-chart").append(row);
  }
  activityRows();
  table(
    "wellness",
    data.wellness.map((w) => [
      day(w.day),
      fmt(w.steps, 0),
      w.resting_hr == null ? "—" : fmt(w.resting_hr, 0) + " ppm",
      hours(w.sleep_seconds),
      fmt(w.sleep_score, 0),
      w.hrv_ms == null ? "—" : fmt(w.hrv_ms, 0) + " ms",
    ]),
  );
  $("include-sleep").checked = data.wellness_options.sleep;
  $("include-hrv").checked = data.wellness_options.hrv;
}
function init() {
  for (const id of ["days", "sport"])
    $(id).addEventListener("change", () =>
      loadDashboard().catch((e) => toast(e.message, true)),
    );
  action("more", () => {
    visibleRows += 30;
    activityRows();
  });
}

export {
  init,
  activityRows,
  drawWeeks,
  loadDashboard,
  dashboardData,
  visibleRows,
  viewVersion,
};
