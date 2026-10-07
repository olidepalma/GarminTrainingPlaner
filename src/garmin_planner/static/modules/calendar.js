import { api, $, sports, hours, fmt, toast, action } from "./core.js";
import { weekdays, loadCoach } from "./coach.js";
import {
  strengthPreview,
  blocksPreview,
  openWorkout,
  previewWorkout,
  defaultStructure,
} from "./workouts.js";
import { loadReview } from "./review.js";
let calendarMonth = new Date(
    new Date().getFullYear(),
    new Date().getMonth(),
    1,
  ),
  calendarVersion = 0;
const sportIcons = {
  running: "🏃",
  trail: "⛰",
  cycling: "🚴",
  swimming: "🏊",
  strength: "🏋",
  triathlon: "🏊🚴🏃",
  other: "●",
};
const statuses = {
  completed: "Realizada",
  planned: "Planificada",
  race: "Prueba",
};
const localISO = (d) =>
  d.getFullYear() +
  "-" +
  String(d.getMonth() + 1).padStart(2, "0") +
  "-" +
  String(d.getDate()).padStart(2, "0");
async function loadCalendar() {
  const own = ++calendarVersion,
    year = calendarMonth.getFullYear(),
    month = calendarMonth.getMonth();
  const data = await api(
    "/api/calendar?year=" + year + "&month=" + (month + 1),
  );
  if (own !== calendarVersion) return;
  data.entries = data.entries.filter(
    (e) => !e.is_draft || $("calendar-show-draft").checked,
  );
  $("calendar-month").textContent = calendarMonth.toLocaleDateString("es-ES", {
    month: "long",
    year: "numeric",
  });
  const grid = $("calendar-grid");
  grid.replaceChildren();
  weekdays.forEach((d) => {
    const header = document.createElement("div");
    header.className = "calendar-weekday";
    header.textContent = d.slice(0, 3);
    grid.append(header);
  });
  const first = new Date(year, month, 1),
    offset = (first.getDay() + 6) % 7,
    today = localISO(new Date());
  for (let i = 0; i < 42; i++) {
    const moment = new Date(year, month, 1 - offset + i),
      iso = localISO(moment),
      cell = document.createElement("article");
    cell.className =
      "calendar-day" +
      (moment.getMonth() !== month ? " outside" : "") +
      (iso === today ? " today" : "");
    cell.setAttribute(
      "aria-label",
      moment.toLocaleDateString("es-ES", {
        weekday: "long",
        day: "numeric",
        month: "long",
      }),
    );
    const number = document.createElement("div");
    number.className = "calendar-day-number";
    number.textContent = String(moment.getDate());
    cell.append(number);
    data.entries
      .filter((e) => e.day === iso)
      .forEach((entry) => {
        const button = document.createElement("button");
        button.className =
          "calendar-entry sport-" +
          (sports[entry.sport] ? entry.sport : "other") +
          " kind-" +
          entry.kind +
          (entry.is_draft ? " draft" : "");
        button.setAttribute(
          "aria-label",
          statuses[entry.kind] +
            ": " +
            entry.title +
            ", " +
            (sports[entry.sport] || "Otros") +
            ", " +
            entry.day,
        );
        const title = document.createElement("span");
        title.textContent =
          (sportIcons[entry.sport] || "●") + " " + entry.title;
        const status = document.createElement("small");
        status.textContent =
          (entry.kind === "completed"
            ? "✓ "
            : entry.kind === "planned"
              ? "◷ "
              : "🏁 ") +
          (entry.is_draft ? "Borrador" : statuses[entry.kind]) +
          (entry.origin === "manual"
            ? " · Propia"
            : entry.origin === "coach"
              ? " · Coach"
              : "");
        button.append(title, status);
        button.addEventListener("click", () => showCalendarDetail(entry));
        cell.append(button);
      });
    grid.append(cell);
  }
  $("calendar-info").textContent =
    data.entries.filter((e) => e.kind === "completed").length +
    " realizadas · " +
    data.entries.filter((e) => e.kind === "planned").length +
    " planificadas · " +
    data.entries.filter((e) => e.kind === "race").length +
    " pruebas. Las celdas grises corresponden a otro mes; navega a ese mes para ver sus entradas.";
}
function showCalendarDetail(entry) {
  $("calendar-detail-title").textContent =
    (sportIcons[entry.sport] || "●") + " " + entry.title;
  const body = $("calendar-detail-body");
  body.replaceChildren();
  const dl = document.createElement("dl");
  const add = (name, value) => {
    if (value == null || value === "") return;
    const term = document.createElement("dt"),
      detail = document.createElement("dd");
    term.textContent = name;
    detail.textContent = String(value);
    dl.append(term, detail);
  };
  const d = entry.detail;
  add("Estado", entry.is_draft ? "Borrador sin aceptar" : statuses[entry.kind]);
  add(
    "Fecha",
    new Date(entry.day + "T12:00:00").toLocaleDateString("es-ES", {
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
    }),
  );
  add("Deporte", sports[entry.sport] || "Otros");
  if (entry.kind === "completed") {
    add("Origen", "Garmin Connect");
    add("Tiempo", hours(d.duration_seconds));
    add("Distancia", fmt(d.distance_m / 1000, 2) + " km");
    add("Desnivel positivo", fmt(d.elevation_m, 0) + " m");
    add(
      "FC media",
      d.average_hr == null ? "No disponible" : fmt(d.average_hr, 0) + " ppm",
    );
  }
  if (entry.kind === "planned") {
    add("Origen", entry.origin === "manual" ? "Sesión propia" : "Coach");
    add("Duración", d.minutes + " min");
    add(
      "Intensidad",
      { easy: "Suave", moderate: "Moderada", hard: "Intensa" }[d.intensity],
    );
    add("Franja", d.slot == null ? "Sin asignar" : String(d.slot + 1));
    add(
      "Horario",
      {
        morning: "Mañana",
        midday: "Mediodía",
        afternoon: "Tarde",
        evening: "Noche",
        any: "Flexible",
      }[d.period],
    );
    add("Sesión larga", d.long_session ? "Sí" : "No");
    add("Indicaciones", d.instructions);
  }
  if (entry.kind === "race") {
    add(
      "Prioridad",
      d.priority === "primary" ? "Objetivo principal" : "Objetivo secundario",
    );
    add("Distancias", d.distances);
    add("Objetivo", d.goal);
  }
  body.append(dl);
  if (entry.kind === "planned") {
    if (d.strength_exercises?.length)
      body.append(strengthPreview(d.strength_exercises));
    const structure = d.structure || d.workout;
    if (structure) body.append(blocksPreview(structure.blocks));
    if (entry.origin === "manual") {
      const edit = document.createElement("button");
      edit.className = "ghost";
      edit.textContent = d.publication?.status
        ? "Crear variante editable"
        : "Editar sesión";
      edit.onclick = () => {
        $("calendar-detail").close();
        openWorkout(d, d.publication?.status ? null : d.id);
      };
      const send = document.createElement("button");
      send.textContent =
        d.publication?.status === "complete"
          ? "Ver envío a Garmin"
          : "Revisar envío a Garmin";
      send.onclick = async () => {
        try {
          $("calendar-detail").close();
          await previewWorkout(d.id);
        } catch (e) {
          toast(e.message, true);
        }
      };
      body.append(edit, send);
    } else if (!entry.is_draft) {
      const copy = document.createElement("button");
      copy.className = "ghost";
      copy.textContent = "Crear copia propia y editar bloques";
      copy.onclick = () => {
        $("calendar-detail").close();
        openWorkout(
          {
            ...d,
            title: "Copia: " + d.title,
            structure: d.workout || defaultStructure(d.minutes),
          },
          null,
        )
          .then(() => {
            if (!d.workout)
              $("workout-editor-hint").textContent =
                "Estos bloques son una plantilla: adáptalos a las indicaciones antes de guardar. Guardar crea otra propuesta propia en el calendario.";
          })
          .catch((error) => toast(error.message));
      };
      body.append(copy);
      if (d.workout) {
        const send = document.createElement("button");
        send.textContent = "Revisar envío a Garmin";
        send.onclick = async () => {
          try {
            const imported = await api("/api/workouts/from-coach", {
              source: d.source_key,
            });
            $("calendar-detail").close();
            await previewWorkout(imported.id);
          } catch (e) {
            toast(e.message, true);
          }
        };
        body.append(send);
      }
    }
  }
  if (entry.kind === "planned") {
    const remove = document.createElement("button");
    remove.className = "ghost";
    remove.textContent = "Borrar sesión";
    remove.onclick = () => {
      removingWorkout = entry;
      $("calendar-detail").close();
      $("workout-remove-summary").textContent =
        entry.title +
        " · " +
        entry.day +
        " · " +
        (entry.is_draft
          ? "Borrador"
          : entry.origin === "manual"
            ? "Sesión propia"
            : "Sesión del coach");
      $("workout-remove-error").textContent = "";
      $("workout-remove-dialog").showModal();
    };
    body.append(remove);
  }
  $("calendar-detail").showModal();
}
let removingWorkout = null;
function setCalendarDay(day) {
  calendarMonth = new Date(day + "T12:00:00");
}
function init() {
  for (const [sport, label] of Object.entries(sports)) {
    const item = document.createElement("span");
    item.className = "calendar-key sport-" + sport;
    item.textContent = sportIcons[sport] + " " + label;
    $("calendar-legend").append(item);
  }
  action("workout-remove-cancel", () => $("workout-remove-dialog").close());
  $("workout-remove-confirm").addEventListener("click", async () => {
    const button = $("workout-remove-confirm");
    button.disabled = true;
    try {
      const entry = removingWorkout;
      const url =
        entry.origin === "manual"
          ? "/api/workouts/" + entry.detail.id + "/remove"
          : "/api/coach/sessions/" +
            entry.detail.source_key +
            "/remove?draft=" +
            Boolean(entry.is_draft);
      await api(url, {});
      $("workout-remove-dialog").close();
      await Promise.all([loadCalendar(), loadReview(), loadCoach()]);
      toast("Sesión borrada del calendario de la web.");
    } catch (error) {
      $("workout-remove-error").textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });
  action("calendar-prev", async () => {
    if (calendarMonth.getFullYear() === 2000 && calendarMonth.getMonth() === 0)
      return;
    calendarMonth = new Date(
      calendarMonth.getFullYear(),
      calendarMonth.getMonth() - 1,
      1,
    );
    await loadCalendar();
  });
  action("calendar-next", async () => {
    if (calendarMonth.getFullYear() === 2100 && calendarMonth.getMonth() === 11)
      return;
    calendarMonth = new Date(
      calendarMonth.getFullYear(),
      calendarMonth.getMonth() + 1,
      1,
    );
    await loadCalendar();
  });
  action("calendar-today", async () => {
    calendarMonth = new Date(
      new Date().getFullYear(),
      new Date().getMonth(),
      1,
    );
    await loadCalendar();
  });
  action("calendar-close", () => $("calendar-detail").close());
  $("calendar-show-draft").addEventListener("change", () =>
    loadCalendar().catch((e) => toast(e.message, true)),
  );
}

export {
  init,
  calendarMonth,
  calendarVersion,
  sportIcons,
  statuses,
  localISO,
  loadCalendar,
  showCalendarDetail,
  removingWorkout,
  setCalendarDay,
};
