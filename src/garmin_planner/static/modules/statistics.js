import { api, fmt, table, $, sports } from "./core.js";
async function loadStatistics() {
  const data = await api("/api/sports-statistics"),
    groups = data.groups || {};
  const names = {
    hr_zones: "Zonas FC",
    power_zones: "Zonas de potencia",
    ftp: "FTP",
    threshold: "Umbral",
    predictions: "Pronósticos",
    vo2: "VO₂ máx.",
  };
  const rows = (key) => groups[key]?.rows || [];
  const state = {
    available: "Disponible",
    empty: "Sin datos",
    failed: "No actualizado; última descarga conservada",
    unrecognized: "Formato de Garmin no reconocido",
  };
  const formatted = (r) => {
    if (r.unit !== "s") return fmt(r.value) + " " + r.unit;
    const seconds = Math.round(r.value);
    return [
      Math.floor(seconds / 3600),
      Math.floor((seconds % 3600) / 60),
      seconds % 60,
    ]
      .map((v) => String(v).padStart(2, "0"))
      .join(":");
  };
  const values = (r) => [
    r.label,
    formatted(r),
    r.sport || "General / sin perfil indicado",
    r.measured_on || "No informada",
  ];
  const withEmpty = (rows) =>
    rows.length ? rows : [["Sin datos disponibles", "—", "—", "—"]];
  renderVo2(rows("vo2"));
  table("statistics-hr", withEmpty(rows("hr_zones").map(values)));
  table("statistics-power", withEmpty(rows("power_zones").map(values)));
  table(
    "statistics-predictions",
    rows("predictions").length
      ? rows("predictions").map((r) => [
          r.label,
          formatted(r),
          r.measured_on || "No informada",
        ])
      : [["Sin datos disponibles", "—", "—"]],
  );
  const predictionState = groups.predictions?.status;
  $("statistics-prediction-state").textContent =
    {
      unrecognized:
        "Garmin respondió, pero no se reconoció el formato. Vuelve a sincronizar después de actualizar la web.",
      failed:
        "La última descarga falló. Se muestran los últimos pronósticos si estaban disponibles.",
      empty: "Garmin no devolvió pronósticos para esta cuenta.",
      available: "",
    }[predictionState] ?? "Pendiente de sincronización con Garmin.";
  $("statistics-update").textContent = data.attempt_at
    ? "Último intento: " + new Date(data.attempt_at).toLocaleString("es-ES")
    : "Sin referencias importadas. Pulsa Sincronizar Garmin.";
  $("statistics-status").textContent = Object.entries(names)
    .map(
      ([k, n]) =>
        `${n}: ${state[groups[k]?.status] || "Pendiente"}${groups[k]?.at ? " (descarga " + new Date(groups[k].at).toLocaleString("es-ES") + ")" : ""}`,
    )
    .join(". ");
  const n = [
    "hr_zones",
    "power_zones",
    "ftp",
    "threshold",
    "vo2",
    "predictions",
  ].reduce((s, k) => s + rows(k).length, 0);
  $("coach-garmin-summary").textContent = n
    ? `${n} referencias importadas disponibles. Revisa sus fechas y perfiles en Estadísticas Garmin.`
    : "Todavía no hay referencias importadas. Sincroniza Garmin; si faltan datos puedes añadirlos aquí.";
}
let vo2Rows = [];
function renderVo2(rows) {
  vo2Rows = rows;
  const selected = $("statistics-vo2-sport").value;
  const profiles = [
    ...new Set(rows.map((r) => (r.sport || "general").toLowerCase())),
  ];
  $("statistics-vo2-sport").replaceChildren();
  profiles.forEach((profile) => {
    const o = document.createElement("option");
    o.value = profile;
    o.textContent =
      sports[profile] ||
      (profile === "generic"
        ? "General (Garmin)"
        : profile === "general"
          ? "Sin perfil indicado"
          : profile);
    $("statistics-vo2-sport").append(o);
  });
  $("statistics-vo2-sport").value = profiles.includes(selected)
    ? selected
    : profiles.find((p) => p === "running") ||
      profiles.find((p) => p === "generic") ||
      profiles[0] ||
      "";
  updateVo2();
}
function updateVo2() {
  const profile = $("statistics-vo2-sport").value,
    unique = new Map();
  vo2Rows
    .filter((r) => (r.sport || "general").toLowerCase() === profile)
    .sort((a, b) => (b.measured_on || "").localeCompare(a.measured_on || ""))
    .forEach((r) => {
      const key = r.measured_on || r.field + ":" + r.value;
      if (!unique.has(key)) unique.set(key, r);
    });
  const latest = [...unique.values()].slice(0, 2);
  table(
    "statistics-metrics",
    latest.length
      ? latest.map((r) => [
          r.label,
          fmt(r.value, 2) + " " + r.unit,
          $("statistics-vo2-sport").selectedOptions[0]?.textContent || "—",
          r.measured_on || "No informada",
        ])
      : [["Sin registros disponibles", "—", "—", "—"]],
  );
  let text =
    "Necesitamos dos registros fechados del mismo perfil para comparar la tendencia.";
  if (
    latest.length === 2 &&
    latest.every((r) => r.measured_on) &&
    latest[0].measured_on !== latest[1].measured_on
  ) {
    const diff = latest[0].value - latest[1].value;
    text =
      (diff > 0 ? "↑ Aumenta" : diff < 0 ? "↓ Disminuye" : "→ Sin cambio") +
      ": " +
      (diff > 0 ? "+" : "") +
      fmt(diff, 2) +
      " ml/kg/min respecto al registro anterior.";
  }
  $("statistics-vo2-trend").textContent = text;
}
function init() {
  $("statistics-vo2-sport").addEventListener("change", updateVo2);
}

export { init, loadStatistics, vo2Rows, renderVo2, updateVo2 };
