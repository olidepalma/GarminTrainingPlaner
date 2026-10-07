import { api, $, action, toast, watch, session } from "./core.js";
import { loadDashboard } from "./overview.js";
async function loadConnections() {
  const c = await api("/api/connections");
  const connected = c.garmin.status === "connected";
  $("garmin-status").textContent = connected ? "Conectada" : "Sin conectar";
  $("garmin-form").hidden = connected;
  $("garmin-disconnect").hidden = !connected;
  $("garmin-name").textContent = connected
    ? c.garmin.name
    : "Actividades y recuperación, directamente desde tu cuenta.";
  $("sync").disabled = !connected;
  $("empty-message").textContent = connected
    ? "No hay actividades en este periodo. Sincroniza o cambia los filtros."
    : "Conecta Garmin para importar tus entrenamientos. Las estadísticas se calculan en tu equipo.";
  $("sync-info").textContent = c.garmin.sync
    ? `Última descarga de actividades: ${new Date(c.garmin.sync.at).toLocaleString("es-ES")}. ${c.garmin.sync.received} actividades revisadas.`
    : "Aún no se ha descargado el historial.";
  if (c.garmin.last_attempt?.status === "failed")
    $("sync-info").textContent +=
      " La última sincronización falló; se conservan los datos anteriores.";
  if (c.garmin.last_attempt?.warnings?.length)
    $("sync-info").textContent +=
      " " + c.garmin.last_attempt.warnings.join(" ");
  const pro = c.pro.status !== "not_connected";
  $("pro-status").textContent =
    c.pro.status === "connected"
      ? "Plan autorizado"
      : c.pro.status === "permission_required"
        ? "Permiso pendiente"
        : "Sin conectar";
  $("pro-name").textContent = pro
    ? c.pro.email
    : "Usa tu plan de ChatGPT en esta aplicación, mediante autorización oficial.";
  $("pro-tools").hidden = !pro;
  $("pro-new").hidden = !pro;
  $("pro-connect").textContent = pro
    ? "Volver a autorizar con ChatGPT"
    : "Continue with ChatGPT";
  $("nightly-info").textContent = c.nightly.enabled
    ? `Sincronización a las ${String(c.nightly.hour).padStart(2, "0")}:00 (${c.nightly.timezone}) mientras el servidor esté encendido. Si lo arrancas después de esa hora, se recupera la ejecución pendiente del día.`
    : "La sincronización automática está desactivada. Puedes sincronizar manualmente.";
  const notice = await api("/api/pro/notice");
  $("pro-notice").textContent = notice.message || "";
}
async function connectPro(new_account = false) {
  if (location.hostname !== "127.0.0.1")
    throw new Error(
      "Para autorizar ChatGPT Pro en el LXC, abre un túnel SSH al puerto configurado del servidor y entra en http://127.0.0.1:8000 (o ese puerto). Inicia sesión allí y conecta Pro. Después puedes seguir usando el dominio HTTPS. Consulta docs/LXC.md.",
    );
  const result = await api("/api/pro/start", { new_account });
  window.location.assign(result.url);
}
function init() {
  action("sync", async () => {
    const job = await api("/api/garmin/sync", {});
    toast("Sincronización en curso…");
    await watch(job.job_id, "toast");
  });
  $("garmin-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.currentTarget.querySelector("button");
    button.disabled = true;
    try {
      const body = {
        email: $("garmin-email").value,
        password: $("garmin-password").value,
      };
      $("garmin-password").value = "";
      const job = await api("/api/garmin/connect", body);
      body.password = "";
      await watch(job.job_id, "garmin-job");
      toast(
        "Garmin conectada. Pulsa Sincronizar Garmin para importar tu historial.",
      );
    } catch (error) {
      toast(error.message, true);
    } finally {
      button.disabled = false;
    }
  });
  $("mfa-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api("/api/jobs/" + session.mfaJob + "/mfa", {
        code: $("mfa-code").value,
      });
      $("mfa-code").value = "";
      $("mfa-form").hidden = true;
    } catch (error) {
      toast(error.message, true);
    }
  });
  action("garmin-disconnect", async () => {
    const j = await api("/api/garmin/disconnect", {});
    await watch(j.job_id, "garmin-job");
    toast("Garmin desconectada. El historial descargado se conserva.");
  });
  action("pro-connect", () => connectPro());
  action("pro-new", () => connectPro(true));
  action("load-models", async () => {
    const data = await api("/api/pro/models");
    $("model").replaceChildren();
    for (const m of data.models) {
      const o = document.createElement("option");
      o.value = m.id;
      o.textContent = m.name;
      $("model").append(o);
    }
    $("pro-test").disabled = !data.models.length;
    if (!data.models.length)
      toast("OpenAI no devolvió modelos disponibles para esta cuenta.", true);
  });
  action("pro-test", async () => {
    const j = await api("/api/pro/test", { model: $("model").value });
    toast("Comprobando ChatGPT Pro…");
    await watch(j.job_id, "toast");
  });
  action("pro-disconnect", async () => {
    const j = await api("/api/pro/disconnect", {});
    await watch(j.job_id, "pro-notice");
    $("model").replaceChildren();
    $("pro-test").disabled = true;
  });
  $("options-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api("/api/wellness-options", {
        sleep: $("include-sleep").checked,
        hrv: $("include-hrv").checked,
      });
      await loadDashboard();
      toast(
        "Preferencias guardadas. Se aplicarán en la próxima sincronización.",
      );
    } catch (error) {
      toast(error.message, true);
    }
  });
}

export { init, loadConnections, connectPro };
