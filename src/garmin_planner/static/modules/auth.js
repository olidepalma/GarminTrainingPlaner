import { api, session, $, tab, action } from "./core.js";
async function boot() {
  const s = await api("/api/session");
  session.csrf = s.csrf;
  $("panel").hidden = !s.authenticated;
  $("login-view").hidden = s.authenticated;
  $("password-label").textContent = s.setup_required
    ? "Crea la contraseña de tu panel"
    : "Contraseña del panel";
  $("local-password").autocomplete = s.setup_required
    ? "new-password"
    : "current-password";
  $("setup-hint").textContent = s.setup_required
    ? "Primera visita: elige al menos 12 caracteres. Esta contraseña es independiente de Garmin y ChatGPT."
    : "Introduce la contraseña que elegiste para este panel.";
  $("login-button").textContent = s.setup_required
    ? "Crear mi acceso"
    : "Entrar";
  if (s.authenticated) {
    tab(
      [
        "#connections",
        "#coach",
        "#statistics",
        "#calendar",
        "#library",
      ].includes(location.hash)
        ? location.hash.slice(1)
        : "overview",
    );
    await session.refresh();
  }
}
function init() {
  $("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    $("login-error").textContent = "";
    $("login-button").disabled = true;
    try {
      await api("/api/session/login", { password: $("local-password").value });
      $("local-password").value = "";
      await boot();
    } catch (error) {
      $("login-error").textContent = error.message;
    } finally {
      $("login-button").disabled = false;
    }
  });
  document
    .querySelectorAll("[data-tab]")
    .forEach((b) => b.addEventListener("click", () => tab(b.dataset.tab)));
  action("go-connections", () => tab("connections"));
  action("logout", async () => {
    await api("/api/session/logout", {});
    session.generation++;
    await boot();
  });
}

export { init, boot };
