const session = {
  csrf: "",
  mfaJob: null,
  generation: 0,
  boot: null,
  refresh: null,
};
const $ = (id) => document.getElementById(id);
const sports = {
  running: "Carrera",
  trail: "Trail",
  cycling: "Ciclismo",
  swimming: "Natación",
  strength: "Fuerza",
  triathlon: "Triatlón",
  other: "Otros",
};
const fmt = (value, digits = 1) =>
  value == null
    ? "—"
    : Number(value).toLocaleString("es-ES", { maximumFractionDigits: digits });
const day = (value) =>
  new Date(value + "T12:00:00").toLocaleDateString("es-ES", {
    day: "2-digit",
    month: "short",
  });
const hours = (seconds) =>
  seconds == null
    ? "—"
    : Math.floor(Math.round(seconds / 60) / 60) +
      " h " +
      (Math.round(seconds / 60) % 60) +
      " min";
function toast(message, error = false) {
  $("toast").textContent = message;
  $("toast").classList.toggle("error", error);
  $("toast").hidden = false;
}
async function api(url, body) {
  const response = await fetch(url, {
    method: body === undefined ? "GET" : "POST",
    headers:
      body === undefined
        ? {}
        : { "Content-Type": "application/json", "X-CSRF-Token": session.csrf },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401 && url !== "/api/session/login") {
      session.generation++;
      await session.boot();
    }
    throw new Error(data.detail || "No se pudo completar la solicitud.");
  }
  return data;
}
function tab(name) {
  for (const id of [
    "overview",
    "connections",
    "coach",
    "statistics",
    "calendar",
    "library",
  ])
    $(id + "-view").hidden = id !== name;
  document
    .querySelectorAll("[data-tab]")
    .forEach((button) =>
      button.classList.toggle("active", button.dataset.tab === name),
    );
  $("page-title").textContent =
    name === "overview"
      ? "Vista general"
      : name === "coach"
        ? "Coach y objetivos"
        : name === "statistics"
          ? "Estadísticas Garmin"
          : name === "calendar"
            ? "Calendario"
            : name === "library"
              ? "Biblioteca"
              : "Conexiones";
  $("page-eyebrow").textContent =
    name === "overview"
      ? "TU ACTIVIDAD, EN CONTEXTO"
      : "TUS DATOS, BAJO TU CONTROL";
  history.replaceState(null, "", "#" + name);
  window.scrollTo(0, 0);
}
function cell(row, text) {
  const td = document.createElement("td");
  td.textContent = text;
  row.append(td);
}
function table(id, rows) {
  const target = $(id);
  target.replaceChildren();
  for (const values of rows) {
    const row = document.createElement("tr");
    values.forEach((value) => cell(row, value));
    target.append(row);
  }
}
async function watch(identifier, target) {
  const own = session.generation;
  while (own === session.generation) {
    const job = await api("/api/jobs/" + identifier);
    $(target).textContent = job.message;
    if (job.status === "waiting_mfa") {
      session.mfaJob = identifier;
      $("mfa-form").hidden = false;
    }
    if (job.status === "failed") {
      $("mfa-form").hidden = true;
      throw new Error(job.message);
    }
    if (job.status === "completed") {
      if (job.kind === "library") {
        await session.refreshLibrary();
        return;
      }
      $("mfa-form").hidden = true;
      session.mfaJob = null;
      if (job.result?.text) {
        $("pro-result").textContent =
          job.result.text +
          (job.result.usage
            ? "\nUso de esta prueba: " + JSON.stringify(job.result.usage)
            : "");
      }
      if (job.kind === "pro" && job.result?.revocation_confirmed === false)
        toast(
          "Desconectada localmente. La revocación remota no se ha confirmado; revisa el acceso en los ajustes de ChatGPT.",
        );
      await session.refresh();
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
}
function action(id, handler) {
  $(id).addEventListener("click", async (event) => {
    event.preventDefault();
    const button = event.currentTarget;
    button.disabled = true;
    try {
      await handler();
    } catch (error) {
      toast(error.message, true);
    } finally {
      button.disabled = false;
    }
  });
}
function init() {}

export {
  init,
  $,
  sports,
  fmt,
  day,
  hours,
  toast,
  api,
  tab,
  cell,
  table,
  watch,
  action,
  session,
};
