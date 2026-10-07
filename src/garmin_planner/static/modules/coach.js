import {
  sports,
  $,
  api,
  table,
  day,
  action,
  toast,
  watch,
  tab,
} from "./core.js";
import { strengthPreview, openWorkout, defaultStructure } from "./workouts.js";
import { renderSourceAudit } from "./library.js";
import { feedbackDirty } from "./review.js";
import { loadCalendar } from "./calendar.js";
let coachState = {},
  coachDirty = false,
  raceCatalog = {};
const availabilityPanels = [];
const weekdays = [
  "Lunes",
  "Martes",
  "Miércoles",
  "Jueves",
  "Viernes",
  "Sábado",
  "Domingo",
];
function field(parent, label, type, value, values = null) {
  const wrap = document.createElement("label");
  wrap.textContent = label;
  const input = document.createElement(
    values ? "select" : type === "textarea" ? "textarea" : "input",
  );
  if (values)
    for (const [v, text] of values) {
      const o = document.createElement("option");
      o.value = v;
      o.textContent = text;
      input.append(o);
    }
  else if (type !== "textarea") input.type = type;
  if (type === "checkbox") input.checked = Boolean(value);
  else input.value = value ?? "";
  wrap.append(input);
  parent.append(wrap);
  return input;
}
const sportOptions = Object.entries(sports).filter(([v]) => v !== "other");
function daySlots(i, slots) {
  const panel = availabilityPanels[i] || document.createElement("fieldset");
  if (!availabilityPanels[i]) {
    $("coach-availability").append(panel);
    availabilityPanels[i] = panel;
  }
  panel.replaceChildren();
  const legend = document.createElement("legend");
  legend.textContent = weekdays[i];
  panel.append(legend);
  const count = field(
    panel,
    "Franjas disponibles",
    "text",
    String(slots.length),
    [0, 1, 2, 3, 4].map((n) => [String(n), n === 0 ? "Descanso" : String(n)]),
  );
  panel.slotFields = [];
  slots.forEach((s, j) => {
    const row = document.createElement("div");
    row.className = "slot-row";
    const heading = document.createElement("h3");
    heading.className = "slot-heading";
    heading.id = `coach-slot-${i}-${j}`;
    heading.textContent = `Franja ${j + 1}`;
    row.setAttribute("role", "group");
    row.setAttribute("aria-labelledby", heading.id);
    row.append(heading);
    const period = field(row, "Momento del día", "text", s.period, [
      ["morning", "Mañana"],
      ["midday", "Mediodía"],
      ["afternoon", "Tarde"],
      ["evening", "Noche"],
      ["any", "Flexible"],
    ]);
    const minutes = field(row, "Minutos", "number", s.minutes);
    minutes.min = 5;
    minutes.max = 480;
    minutes.required = true;
    const preferredSport = field(
      row,
      "Preferencia de deporte",
      "text",
      s.preferred_sport || "",
      [
        ["", "Sin preferencia"],
        ["running", "Carrera / atletismo"],
        ["trail", "Trail"],
        ["cycling", "Ciclismo"],
        ["swimming", "Natación"],
        ["strength", "Fuerza"],
      ],
    );
    preferredSport.parentElement.classList.add("slot-preference");
    panel.slotFields.push({ period, minutes, preferredSport });
    panel.append(row);
  });
  count.addEventListener("change", () => {
    const current = panel.slotFields.map((f) => ({
      period: f.period.value,
      minutes: Number(f.minutes.value),
      preferred_sport: f.preferredSport.value || null,
    }));
    daySlots(
      i,
      Array.from(
        { length: Number(count.value) },
        (_, j) =>
          current[j] || {
            period: j === 0 ? "morning" : "afternoon",
            minutes: 60,
          },
      ),
    );
    coachDirty = true;
  });
}
function eventRow(event = { priority: "secondary", sport: "triathlon" }) {
  const row = document.createElement("fieldset");
  const legend = document.createElement("legend");
  legend.textContent = "Prueba";
  row.append(legend);
  row.fields = {};
  row.eventId = event.id || crypto.randomUUID();
  for (const [key, label, type, options] of [
    ["name", "Nombre", "text"],
    ["day", "Fecha", "date"],
    ["sport", "Modalidad", "text", sportOptions],
    [
      "priority",
      "Prioridad",
      "text",
      [
        ["primary", "Objetivo principal"],
        ["secondary", "Objetivo secundario"],
      ],
    ],
    [
      "distance_code",
      "Distancia estándar",
      "text",
      [["other", "Otra / personalizada"]],
    ],
    ["distances", "Distancias por disciplina", "text"],
    ["goal", "Objetivo de esta prueba", "text"],
  ]) {
    row.fields[key] = field(row, label, type, event[key], options);
    if (["name", "day"].includes(key)) row.fields[key].required = true;
  }
  const refreshDistances = () => {
    const select = row.fields.distance_code,
      saved = select.value;
    select.replaceChildren();
    for (const [code, item] of Object.entries(
      raceCatalog[row.fields.sport.value] || {},
    )) {
      const o = document.createElement("option");
      o.value = code;
      o.textContent = item[0];
      select.append(o);
    }
    const other = document.createElement("option");
    other.value = "other";
    other.textContent = "Otra / personalizada";
    select.append(other);
    select.value = [...select.options].some((o) => o.value === saved)
      ? saved
      : "other";
    showDistance();
  };
  const showDistance = () => {
    const code = row.fields.distance_code.value,
      standard = raceCatalog[row.fields.sport.value]?.[code];
    row.fields.distances.parentElement.hidden = Boolean(standard);
    row.fields.distances.disabled = Boolean(standard);
    if (standard) row.fields.distances.value = standard[1];
  };
  row.fields.distance_code.value = event.distance_code || "other";
  refreshDistances();
  if (event.distance_code && raceCatalog[event.sport]?.[event.distance_code])
    row.fields.distance_code.value = event.distance_code;
  showDistance();
  row.fields.sport.addEventListener("change", () => {
    row.fields.distance_code.value = "other";
    row.fields.distances.value = "";
    refreshDistances();
  });
  row.fields.distance_code.addEventListener("change", () => {
    if (row.fields.distance_code.value === "other")
      row.fields.distances.value = "";
    showDistance();
  });
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "ghost";
  remove.textContent = "Eliminar prueba";
  remove.onclick = () => {
    coachDirty = true;
    row.remove();
  };
  row.append(remove);
  $("coach-events").append(row);
}
function sessionRow(
  s = {
    day: $("coach-start").value,
    sport: "running",
    intensity: "easy",
    minutes: 30,
    title: "",
    instructions: "",
  },
) {
  const row = document.createElement("fieldset");
  row.fields = {};
  for (const [key, label, type, options] of [
    ["day", "Fecha", "date"],
    [
      "sport",
      "Deporte",
      "text",
      sportOptions.filter(([v]) => v !== "triathlon"),
    ],
    ["title", "Sesión", "text"],
    ["minutes", "Minutos", "number"],
    [
      "intensity",
      "Intensidad",
      "text",
      [
        ["easy", "Suave"],
        ["moderate", "Moderada"],
        ["hard", "Intensa"],
      ],
    ],
    [
      "slot",
      "Franja disponible",
      "text",
      [
        ["", "Sin asignar (perfil anterior)"],
        ["0", "Franja 1"],
        ["1", "Franja 2"],
        ["2", "Franja 3"],
        ["3", "Franja 4"],
      ],
    ],
    ["long_session", "Tirada / salida larga", "checkbox"],
    ["instructions", "Indicaciones", "textarea"],
  ])
    row.fields[key] = field(row, label, type, s[key], options);
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "ghost";
  remove.textContent = "Eliminar sesión";
  remove.onclick = () => row.remove();
  row.append(remove);
  row.strengthExercises = s.strength_exercises || [];
  if (row.strengthExercises.length)
    row.append(strengthPreview(row.strengthExercises));
  row.workoutStructure = s.workout || null;
  const blocks = document.createElement("button");
  blocks.type = "button";
  blocks.className = "ghost";
  blocks.textContent = "Editar bloques de la sesión";
  blocks.onclick = () =>
    openWorkout(
      {
        title: row.fields.title.value,
        day: row.fields.day.value,
        sport: row.fields.sport.value,
        minutes: Number(row.fields.minutes.value),
        instructions: row.fields.instructions.value,
        structure:
          row.workoutStructure ||
          defaultStructure(Number(row.fields.minutes.value)),
      },
      null,
      (body) => {
        row.workoutStructure = body.structure;
        for (const key of ["title", "day", "sport", "minutes", "instructions"])
          row.fields[key].value = body[key];
      },
    );
  row.append(blocks);
  $("coach-sessions").append(row);
}
function readRows(id) {
  return [...$(id).children].map((row) =>
    Object.fromEntries(
      Object.entries(row.fields).map(([k, e]) => [
        k,
        e.type === "checkbox"
          ? e.checked
          : e.type === "number"
            ? Number(e.value)
            : e.value,
      ]),
    ),
  );
}
function modelOption(id, value, label = value) {
  if (value && ![...$(id).options].some((o) => o.value === value)) {
    const o = document.createElement("option");
    o.value = value;
    o.textContent = label;
    $(id).append(o);
  }
  $(id).value = value;
}
async function loadCoach() {
  coachDirty = false;
  raceCatalog = (await api("/api/race-distances")).catalog;
  coachState = await api("/api/coach");
  const p = coachState.setup?.profile;
  if (p) {
    for (const [id, key] of [
      ["coach-sex", "sex"],
      ["coach-age", "age"],
      ["coach-weight", "weight_kg"],
      ["coach-height", "height_cm"],
      ["coach-strength-equipment", "strength_equipment"],
      ["coach-strength-loads", "strength_loads"],
    ])
      $(id).value = p[key] ?? "";
    $("coach-strength-experience").value =
      p.strength_experience || "intermediate";
    $("coach-experience").value = p.experience;
    $("coach-max-days").value = p.max_days;
    $("coach-strength").checked = p.strength;
    $("coach-wellness").checked = p.use_wellness;
    $("coach-zones").value = p.zones;
    $("coach-notes").value = p.notes;
    weekdays.forEach((_, i) =>
      daySlots(
        i,
        p.slots?.[i] ||
          (p.availability[i] > 0
            ? [{ period: "any", minutes: p.availability[i] }]
            : []),
      ),
    );
    $("coach-garmin-zones").checked = p.use_garmin_zones !== false;
    document
      .querySelectorAll("[data-sport]")
      .forEach((e) => (e.checked = p.sports.includes(e.dataset.sport)));
    $("coach-long-run").value = p.long_run_day ?? "";
    $("coach-long-bike").value = p.long_bike_day ?? "";
    modelOption("coach-initial-model", p.initial_model);
    modelOption("coach-weekly-model", p.weekly_model);
  }
  $("coach-events").replaceChildren();
  (
    coachState.setup?.events || [{ priority: "primary", sport: "triathlon" }]
  ).forEach(eventRow);
  const d = coachState.draft;
  $("coach-draft-card").hidden = !d;
  $("coach-sessions").replaceChildren();
  if (d) {
    $("coach-strategy").value = d.plan.strategy;
    $("coach-rationale").value = d.plan.rationale;
    d.plan.sessions.forEach(sessionRow);
    $("coach-draft-info").textContent =
      `Modelo: ${d.model} · Contexto: ${d.context_characters} caracteres · Uso: ${JSON.stringify(d.usage || {})}`;
    $("coach-warnings").textContent = d.warnings.join(" ");
    renderSourceAudit(d);
  }
  $("coach-accepted-sources-card").hidden = !coachState.accepted;
  if (coachState.accepted)
    renderSourceAudit(coachState.accepted, "coach-accepted-sources");
  table(
    "coach-calendar",
    (coachState.calendar || [])
      .sort((a, b) => a.day.localeCompare(b.day))
      .map((s) => [
        day(s.day) + " " + s.day.slice(0, 4),
        sports[s.sport],
        s.title + (s.slot != null ? " · Franja " + (s.slot + 1) : ""),
        s.minutes,
        s.instructions,
      ]),
  );
}
function init() {
  for (const [v, label] of sportOptions.filter(
    ([v]) => !["strength", "triathlon"].includes(v),
  )) {
    const input = field(
      $("coach-sports"),
      label,
      "checkbox",
      ["running", "cycling", "swimming"].includes(v),
    );
    input.dataset.sport = v;
  }
  weekdays.forEach((_, i) =>
    daySlots(i, i === 6 ? [] : [{ period: "any", minutes: 60 }]),
  );
  for (const id of ["coach-long-run", "coach-long-bike"]) {
    for (const [v, label] of [
      ["", "Sin preferencia"],
      ...weekdays.map((d, i) => [String(i), d]),
    ]) {
      const o = document.createElement("option");
      o.value = v;
      o.textContent = label;
      $(id).append(o);
    }
  }
  $("coach-start").value = new Date(
    Date.now() - new Date().getTimezoneOffset() * 60000,
  )
    .toISOString()
    .slice(0, 10);
  action("coach-add-event", () => {
    coachDirty = true;
    eventRow();
  });
  action("coach-add-session", () => sessionRow());
  action("coach-models", async () => {
    coachDirty = true;
    const data = await api("/api/pro/models");
    for (const id of ["coach-initial-model", "coach-weekly-model"]) {
      const saved = $(id).value;
      $(id).replaceChildren();
      for (const m of data.models) modelOption(id, m.id, m.name);
      if (data.models.some((m) => m.id === saved)) $(id).value = saved;
      else {
        const wanted = id === "coach-initial-model" ? "astra" : "sol";
        $(id).value =
          data.models.find((m) => m.id.includes(wanted))?.id ||
          data.models[0]?.id ||
          "";
      }
    }
  });
  $("coach-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const preference = (id) =>
        $(id).value === "" ? null : Number($(id).value);
      const profile = {
        sex: $("coach-sex").value || null,
        age: preference("coach-age"),
        weight_kg: preference("coach-weight"),
        height_cm: preference("coach-height"),
        strength_experience: $("coach-strength-experience").value,
        strength_equipment: $("coach-strength-equipment").value,
        strength_loads: $("coach-strength-loads").value,
        experience: $("coach-experience").value,
        sports: [...document.querySelectorAll("[data-sport]:checked")].map(
          (e) => e.dataset.sport,
        ),
        slots: availabilityPanels.map((p) =>
          p.slotFields.map((f) => ({
            period: f.period.value,
            minutes: Number(f.minutes.value),
            preferred_sport: f.preferredSport.value || null,
          })),
        ),
        use_garmin_zones: $("coach-garmin-zones").checked,
        availability: availabilityPanels.map((p) =>
          p.slotFields.reduce((sum, f) => sum + Number(f.minutes.value), 0),
        ),
        max_days: Number($("coach-max-days").value),
        strength: $("coach-strength").checked,
        long_run_day: preference("coach-long-run"),
        long_bike_day: preference("coach-long-bike"),
        zones: $("coach-zones").value,
        notes: $("coach-notes").value,
        use_wellness: $("coach-wellness").checked,
        initial_model: $("coach-initial-model").value,
        weekly_model: $("coach-weekly-model").value,
      };
      const events = readRows("coach-events").map((r, i) => ({
        ...r,
        id: $("coach-events").children[i].eventId,
      }));
      await api("/api/coach/setup", { profile, events });
      coachDirty = false;
      toast("Perfil y objetivos guardados.");
    } catch (error) {
      toast(error.message, true);
    }
  });
  action("coach-generate", async () => {
    if (feedbackDirty)
      throw new Error(
        "Guarda la revisión de la semana para incluir tus sensaciones en el borrador.",
      );
    if (coachDirty)
      throw new Error(
        "Guarda los cambios del perfil y objetivos antes de generar.",
      );
    const j = await api("/api/coach/generate", {
      start: $("coach-start").value,
      mode: $("coach-mode").value,
    });
    $("coach-job").textContent =
      "Preparando borrador con tu contexto deportivo…";
    await watch(j.job_id, "coach-job");
    tab("coach");
  });
  action("coach-accept", async () => {
    if (coachDirty) throw new Error("Guarda primero los cambios del perfil.");
    await api("/api/coach/accept", {
      draft_id: coachState.draft.id,
      plan: {
        citations: coachState.draft.plan.citations || [],
        strategy: $("coach-strategy").value,
        rationale: $("coach-rationale").value,
        sessions: readRows("coach-sessions").map((s, i) => ({
          ...s,
          slot: s.slot === "" ? null : Number(s.slot),
          workout: $("coach-sessions").children[i].workoutStructure,
          strength_exercises:
            s.sport === "strength"
              ? $("coach-sessions").children[i].strengthExercises
              : [],
        })),
      },
    });
    await Promise.all([loadCoach(), loadCalendar()]);
    toast("Semana revisada guardada en el calendario.");
  });
  $("coach-form").addEventListener("input", () => {
    coachDirty = true;
  });
  $("coach-form").addEventListener("change", () => {
    coachDirty = true;
  });
}

export {
  init,
  coachState,
  coachDirty,
  raceCatalog,
  availabilityPanels,
  weekdays,
  field,
  sportOptions,
  daySlots,
  eventRow,
  sessionRow,
  readRows,
  modelOption,
  loadCoach,
};
