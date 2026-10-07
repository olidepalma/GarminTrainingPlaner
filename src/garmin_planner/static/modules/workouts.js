import { $, api, sports, action, toast, watch } from "./core.js";
import { setCalendarDay, loadCalendar } from "./calendar.js";
import { loadReview } from "./review.js";
let editingWorkout = null,
  draftWorkoutSave = null,
  sendWorkout = null,
  workoutOptions = { strength_categories: [] };
const blockNames = {
  warmup: "Calentamiento",
  exercise: "Ejercicio",
  recovery: "Recuperación",
  rest: "Descanso",
  cooldown: "Vuelta a la calma",
  repeat: "Repetir bloque",
};
const swimStrokes = {
  "": "Sin especificar",
  free: "Crol",
  backstroke: "Espalda",
  breaststroke: "Braza",
  any_stroke: "Libre elección",
  butterfly: "Mariposa",
  drill: "Técnica",
};
const swimEquipment = {
  "": "Sin material",
  kickboard: "Tabla",
  pull_buoy: "Pull buoy",
  fins: "Aletas",
  paddles: "Palas",
  snorkel: "Snorkel",
};
function defaultStructure(minutes = 20) {
  const total = Number(minutes) * 60,
    warm = Math.min(300, total / 5),
    cool = warm;
  return {
    pool_length: 25,
    blocks: [
      { kind: "warmup", duration_type: "time", value: warm },
      { kind: "exercise", duration_type: "time", value: total - warm - cool },
      { kind: "cooldown", duration_type: "time", value: cool },
    ],
  };
}
function workoutTime(seconds) {
  const n = Math.round(Number(seconds));
  return Math.floor(n / 60) + ":" + String(n % 60).padStart(2, "0");
}
function workoutSeconds(text) {
  if (!/^\d+:[0-5]\d$/.test(text))
    throw new Error("Indica el tiempo en minutos:segundos, por ejemplo 5:30.");
  const [m, s] = text.split(":").map(Number);
  const total = m * 60 + s;
  if (total <= 0 || total > 86400)
    throw new Error(
      "El tiempo de cada paso debe ser mayor que 0:00 y no superar 1440:00.",
    );
  return total;
}
function updateWorkoutDuration() {
  try {
    const walk = (b) =>
      b.kind === "repeat"
        ? b.iterations * b.steps.reduce((sum, step) => sum + walk(step), 0)
        : b.duration_type === "time"
          ? b.value
          : 0;
    const allTime = (b) =>
      b.kind === "repeat" ? b.steps.every(allTime) : b.duration_type === "time";
    const blocks = [...$("workout-blocks").children].map((c) => c.readBlock());
    const total = blocks.reduce((sum, b) => sum + walk(b), 0),
      estimate = Number($("workout-minutes").value) * 60;
    const warn =
      blocks.length &&
      total !== estimate &&
      (blocks.every(allTime) || total > estimate);
    $("workout-duration-warning").textContent = warn
      ? `Los bloques por tiempo suman ${workoutTime(total)} y la duración estimada es ${workoutTime(estimate)}. Puedes guardar sin que coincidan.`
      : "";
  } catch {
    $("workout-duration-warning").textContent = "";
  }
}
function strengthPreview(exercises) {
  const section = document.createElement("section"),
    heading = document.createElement("h3");
  heading.textContent = "Ejercicios de fuerza";
  section.append(heading);
  const list = document.createElement("ol");
  for (const exercise of exercises) {
    const item = document.createElement("li"),
      name = document.createElement("strong"),
      detail = document.createElement("p");
    name.textContent = exercise.name;
    detail.textContent =
      `${exercise.sets} series · ${exercise.repetitions} · Carga: ${exercise.load} · Descanso: ${workoutTime(exercise.rest_seconds)} min:s` +
      (exercise.cues ? " · " + exercise.cues : "");
    item.append(name, detail);
    list.append(item);
  }
  section.append(list);
  return section;
}
function blocksPreview(blocks) {
  const list = document.createElement("ol");
  for (const b of blocks) {
    const item = document.createElement("li");
    item.textContent =
      blockNames[b.kind] +
      (b.kind === "repeat"
        ? " × " + b.iterations
        : b.duration_type === "lap"
          ? " · Hasta pulsar Lap"
          : " · " +
            (b.duration_type === "time"
              ? workoutTime(b.value) + " min:s"
              : b.value +
                " " +
                { distance: "m", reps: "repeticiones" }[b.duration_type])) +
      (b.target && b.target !== "none"
        ? " · " + (b.target === "hr_zone" ? "FC" : "Potencia") + " Z" + b.zone
        : "") +
      (b.stroke ? " · " + (swimStrokes[b.stroke] || b.stroke) : "") +
      (b.equipment ? " · " + (swimEquipment[b.equipment] || b.equipment) : "") +
      (b.notes ? " · " + b.notes : "");
    if (b.kind === "repeat") item.append(blocksPreview(b.steps));
    list.append(item);
  }
  return list;
}
function editorField(parent, label, type, value, choices) {
  const wrap = document.createElement("label");
  wrap.textContent = label;
  let input;
  if (choices) {
    input = document.createElement("select");
    for (const [key, text] of Object.entries(choices))
      input.append(new Option(text, key));
  } else {
    input = document.createElement(type === "textarea" ? "textarea" : "input");
    if (type !== "textarea") input.type = type;
  }
  input.value = value ?? "";
  wrap.append(input);
  parent.append(wrap);
  return input;
}
function blockEditor(
  container,
  b = { kind: "exercise", duration_type: "time", value: 60 },
  depth = 0,
) {
  const root = document.createElement("section");
  root.className = "workout-block";
  const heading = document.createElement("h4");
  heading.textContent = blockNames[b.kind] || "Paso";
  root.append(heading);
  const fields = document.createElement("div");
  fields.className = "workout-step-fields";
  root.append(fields);
  let read;
  if (b.kind === "repeat") {
    const count = editorField(
      fields,
      "Repeticiones del bloque",
      "number",
      b.iterations || 2,
    );
    count.min = "2";
    count.max = "50";
    const children = document.createElement("div");
    root.append(children);
    (
      b.steps || [
        { kind: "exercise", duration_type: "time", value: 60 },
        { kind: "rest", duration_type: "time", value: 30 },
      ]
    ).forEach((step) => blockEditor(children, step, depth + 1));
    const add = document.createElement("button");
    add.type = "button";
    add.className = "ghost";
    add.textContent = "Añadir paso dentro del bloque";
    add.onclick = () => blockEditor(children, undefined, depth + 1);
    root.append(add);
    if (depth < 2) {
      const nested = document.createElement("button");
      nested.type = "button";
      nested.className = "ghost";
      nested.textContent = "Añadir repetición dentro del bloque";
      nested.onclick = () =>
        blockEditor(children, { kind: "repeat", iterations: 2 }, depth + 1);
      root.append(nested);
    }
    read = () => ({
      kind: "repeat",
      iterations: Number(count.value),
      steps: [...children.children].map((c) => c.readBlock()),
    });
  } else {
    const kind = editorField(
      fields,
      "Tipo de paso",
      "",
      b.kind || "exercise",
      Object.fromEntries(
        Object.entries(blockNames).filter(([k]) => k !== "repeat"),
      ),
    );
    const unit = editorField(
      fields,
      "Fin del paso",
      "",
      b.duration_type || "time",
      {
        time: "Tiempo (minutos:segundos)",
        distance: "Distancia (metros)",
        lap: "Hasta pulsar Lap",
        reps: "Repeticiones (fuerza)",
      },
    );
    const value = editorField(fields, "Cantidad", "number", b.value ?? 60);
    let previousUnit = null;
    const label = document.createTextNode("");
    value.parentElement.firstChild.replaceWith(label);
    const target = editorField(fields, "Objetivo", "", b.target || "none", {
      none: "Sin objetivo / esfuerzo en notas",
      hr_zone: "Zona de frecuencia cardiaca",
      power_zone: "Zona de potencia (bici)",
    });
    const zone = editorField(fields, "Zona", "number", b.zone ?? 2);
    zone.min = "1";
    zone.max = "7";
    const stroke = editorField(
        fields,
        "Estilo de natación",
        "",
        b.stroke || "",
        swimStrokes,
      ),
      equipment = editorField(
        fields,
        "Material de natación",
        "",
        b.equipment || "",
        swimEquipment,
      );
    const category = editorField(
      fields,
      "Categoría Garmin de fuerza",
      "",
      b.category || "",
      Object.fromEntries([
        ["", "Sin categoría"],
        ...workoutOptions.strength_categories.map((c) => [c, c]),
      ]),
    );
    const notes = editorField(
      root,
      "Notas del paso",
      "textarea",
      b.notes || "",
    );
    notes.maxLength = 500;
    notes.rows = 2;
    const update = () => {
      if (previousUnit !== unit.value) {
        value.type = unit.value === "time" ? "text" : "number";
        value.removeAttribute("pattern");
        if (unit.value === "time") {
          value.value = workoutTime(
            previousUnit === null ? (b.value ?? 60) : 60,
          );
          value.pattern = "[0-9]+:[0-5][0-9]";
          value.placeholder = "5:30";
          value.inputMode = "text";
        } else {
          value.value =
            previousUnit === null
              ? (b.value ?? 100)
              : unit.value === "reps"
                ? 10
                : 100;
          value.min = "1";
          value.max = "86400";
        }
        previousUnit = unit.value;
      }
      label.textContent =
        unit.value === "time"
          ? "Duración (minutos:segundos)"
          : unit.value === "distance"
            ? "Distancia (metros)"
            : unit.value === "reps"
              ? "Cantidad de repeticiones"
              : "Cantidad";
      value.required = unit.value !== "lap";
      value.disabled = unit.value === "lap";
      zone.disabled = target.value === "none";
      const swim = $("workout-sport").value === "swimming";
      stroke.parentElement.hidden = !swim;
      equipment.parentElement.hidden = !swim;
      category.parentElement.hidden = $("workout-sport").value !== "strength";
    };
    unit.onchange = update;
    target.onchange = update;
    root.updateSport = update;
    update();
    read = () => ({
      kind: kind.value,
      duration_type: unit.value,
      value:
        unit.value === "lap"
          ? null
          : unit.value === "time"
            ? workoutSeconds(value.value)
            : Number(value.value),
      target: target.value,
      zone: target.value === "none" ? null : Number(zone.value),
      stroke: $("workout-sport").value === "swimming" ? stroke.value : "",
      equipment: $("workout-sport").value === "swimming" ? equipment.value : "",
      category: $("workout-sport").value === "strength" ? category.value : "",
      notes: notes.value,
    });
  }
  const controls = document.createElement("div");
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "ghost";
  remove.textContent = "Eliminar bloque";
  remove.onclick = () => {
    root.remove();
    updateWorkoutDuration();
  };
  const up = document.createElement("button");
  up.type = "button";
  up.className = "ghost";
  up.textContent = "Subir bloque";
  up.onclick = () => {
    if (root.previousElementSibling)
      container.insertBefore(root, root.previousElementSibling);
  };
  controls.append(up, remove);
  root.append(controls);
  root.readBlock = read;
  container.append(root);
  updateWorkoutDuration();
}
async function openWorkout(data = {}, identifier = null, onSave = null) {
  workoutOptions = await api("/api/workout-options");
  editingWorkout = identifier;
  draftWorkoutSave = onSave;
  $("workout-save").textContent = onSave
    ? "Guardar bloques en borrador"
    : "Guardar sesión en calendario";
  $("workout-editor-hint").textContent = onSave
    ? "Edita los bloques del borrador. El calendario cambiará cuando aceptes la semana."
    : "Guardar añade una propuesta al calendario local. El envío a Garmin es un paso posterior. Tiempo en minutos:segundos, distancia en metros.";
  $("workout-editor-title").textContent = identifier
    ? "Editar sesión propia"
    : "Crear sesión propia";
  $("workout-title").value = data.title || "";
  $("workout-day").value =
    data.day ||
    new Date(Date.now() - new Date().getTimezoneOffset() * 60000)
      .toISOString()
      .slice(0, 10);
  $("workout-sport").value = data.sport || "running";
  $("workout-minutes").value = data.minutes || 20;
  $("workout-notes").value = data.instructions || "";
  $("workout-pool").value = data.structure?.pool_length || 25;
  $("workout-blocks").replaceChildren();
  (data.structure || defaultStructure(data.minutes || 20)).blocks.forEach((b) =>
    blockEditor($("workout-blocks"), b),
  );
  $("workout-pool").hidden = $("workout-sport").value !== "swimming";
  document.querySelector('label[for="workout-pool"]').hidden =
    $("workout-pool").hidden;
  $("workout-editor-error").textContent = "";
  updateWorkoutDuration();
  $("workout-editor").showModal();
}
async function previewWorkout(identifier) {
  const [preview, saved] = await Promise.all([
    api("/api/workouts/" + identifier + "/preview"),
    api("/api/workouts/" + identifier),
  ]);
  sendWorkout = { id: identifier, revision: preview.revision };
  $("workout-send-summary").textContent =
    saved.title +
    " · " +
    saved.day +
    " · " +
    sports[saved.sport] +
    " · " +
    saved.minutes +
    " min";
  $("workout-send-blocks").replaceChildren(
    blocksPreview(saved.structure.blocks),
  );
  $("workout-send-warnings").textContent = preview.warnings.join(" ");
  $("workout-send-json").textContent = JSON.stringify(preview.payload, null, 2);
  $("workout-send-status").textContent =
    saved.publication.status === "complete"
      ? "Creada y programada en Garmin. ID: " +
        saved.publication.workout_id +
        ". Sincroniza tu reloj con Garmin Connect."
      : saved.publication.status
        ? "Estado del envío anterior: " + saved.publication.status
        : "";
  $("workout-send-confirm").disabled = Boolean(saved.publication.status);
  $("workout-send-dialog").showModal();
}
function init() {
  action("calendar-create", () => openWorkout());
  action("workout-add-step", () => blockEditor($("workout-blocks")));
  action("workout-add-repeat", () =>
    blockEditor($("workout-blocks"), { kind: "repeat", iterations: 2 }),
  );
  action("workout-editor-close", () => $("workout-editor").close());
  $("workout-sport").addEventListener("change", () => {
    $("workout-pool").hidden = $("workout-sport").value !== "swimming";
    document.querySelector('label[for="workout-pool"]').hidden =
      $("workout-pool").hidden;
    $("workout-blocks")
      .querySelectorAll("section")
      .forEach((s) => s.updateSport?.());
  });
  $("workout-form").addEventListener("input", updateWorkoutDuration);
  $("workout-form").addEventListener("change", updateWorkoutDuration);
  $("workout-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    $("workout-save").disabled = true;
    $("workout-editor-error").textContent = "";
    try {
      const body = {
        title: $("workout-title").value,
        day: $("workout-day").value,
        sport: $("workout-sport").value,
        minutes: Number($("workout-minutes").value),
        instructions: $("workout-notes").value,
        structure: {
          pool_length: Number($("workout-pool").value),
          blocks: [...$("workout-blocks").children].map((c) => c.readBlock()),
        },
      };
      if (draftWorkoutSave) {
        await api("/api/workouts/validate", body);
        draftWorkoutSave(body);
        $("workout-editor").close();
        toast("Bloques actualizados en el borrador.");
        return;
      }
      await api(
        "/api/workouts" + (editingWorkout ? "/" + editingWorkout : ""),
        body,
      );
      $("workout-editor").close();
      setCalendarDay(body.day);
      await Promise.all([loadCalendar(), loadReview()]);
      toast(
        "Sesión guardada en el calendario local. Abre su detalle para revisar el envío a Garmin.",
      );
    } catch (error) {
      $("workout-editor-error").textContent = error.message;
    } finally {
      $("workout-save").disabled = false;
    }
  });
  $("workout-send-confirm").addEventListener("click", async () => {
    const button = $("workout-send-confirm");
    button.disabled = true;
    try {
      const job = await api("/api/workouts/" + sendWorkout.id + "/send", {
        revision: sendWorkout.revision,
      });
      await watch(job.job_id, "workout-send-status");
      const saved = await api("/api/workouts/" + sendWorkout.id);
      $("workout-send-status").textContent =
        "Creada y programada en Garmin. ID: " +
        saved.publication.workout_id +
        ". Sincroniza el reloj con Garmin Connect.";
    } catch (error) {
      $("workout-send-status").textContent = error.message;
      const saved = await api("/api/workouts/" + sendWorkout.id).catch(
        () => null,
      );
      button.disabled = Boolean(saved?.publication.status);
    }
  });
  action("workout-send-close", () => $("workout-send-dialog").close());
}

export {
  init,
  editingWorkout,
  draftWorkoutSave,
  sendWorkout,
  workoutOptions,
  blockNames,
  swimStrokes,
  swimEquipment,
  defaultStructure,
  workoutTime,
  workoutSeconds,
  updateWorkoutDuration,
  strengthPreview,
  blocksPreview,
  editorField,
  blockEditor,
  openWorkout,
  previewWorkout,
};
