import { $, api, toast, watch, session } from "./core.js";
function renderSourceAudit(draft, target = "coach-source-audit") {
  const root = $(target);
  root.replaceChildren();
  const title = document.createElement("h3");
  title.textContent = "Fragmentos enviados al coach";
  root.append(title);
  if (!draft.sources_snapshot?.length) {
    const p = document.createElement("p");
    p.textContent = "No se enviaron fragmentos de la Biblioteca.";
    root.append(p);
    return;
  }
  for (const source of draft.sources_snapshot) {
    const details = document.createElement("details"),
      summary = document.createElement("summary"),
      text = document.createElement("p");
    summary.textContent =
      source.title +
      " · versión " +
      source.version +
      " · " +
      source.locator +
      ((draft.plan.citations || []).includes(source.id)
        ? " · Citada por el coach"
        : " · Enviada, sin cita");
    text.textContent = source.text;
    details.append(summary, text);
    root.append(details);
  }
}
async function loadLibrary() {
  const data = await api("/api/library"),
    selected = $("library-target").value;
  $("coach-library-summary").textContent =
    data.documents.filter((d) => d.enabled && d.active != null).length +
    " fuentes seleccionadas para nuevas planificaciones. Puedes revisarlas en Biblioteca.";
  $("library-target").replaceChildren(new Option("Nueva fuente", ""));
  $("library-documents").replaceChildren();
  if (!data.documents.length) {
    const p = document.createElement("p");
    p.className = "muted";
    p.textContent =
      "Todavía no hay fuentes. Puedes subir aquí tu EPUB cuando quieras.";
    $("library-documents").append(p);
  }
  for (const doc of data.documents) {
    $("library-target").append(new Option(doc.title, doc.id));
    const item = document.createElement("section");
    item.className = "library-document";
    const heading = document.createElement("h3");
    heading.textContent = doc.title;
    const by = document.createElement("p");
    by.className = "muted";
    by.textContent =
      (doc.author || "Autor sin indicar") +
      " · Versión activa: " +
      (doc.active ?? "ninguna");
    const label = document.createElement("label");
    label.className = "check";
    const check = document.createElement("input");
    check.type = "checkbox";
    check.checked = doc.enabled;
    check.disabled = doc.active == null;
    label.append(
      check,
      document.createTextNode("Usar en el coach: " + doc.title),
    );
    check.addEventListener("change", async () => {
      check.disabled = true;
      try {
        await api("/api/library/" + doc.id + "/enabled", {
          enabled: check.checked,
        });
        await loadLibrary();
        toast("Selección de fuentes guardada para futuras generaciones.");
      } catch (error) {
        check.checked = !check.checked;
        toast(error.message, true);
      } finally {
        check.disabled = false;
      }
    });
    const newest = doc.versions[0],
      process = document.createElement("button");
    process.type = "button";
    process.textContent =
      newest.status === "ready"
        ? "Versión procesada"
        : doc.active == null
          ? "Procesar documento"
          : "Procesar actualización";
    process.disabled = newest.status === "ready";
    process.addEventListener("click", async () => {
      process.disabled = true;
      try {
        const job = await api("/api/library/" + doc.id + "/process", {});
        $("library-job").textContent =
          "Extrayendo e indexando texto en tu equipo…";
        await watch(job.job_id, "library-job");
        toast(
          "Documento procesado. Revisa la muestra y selecciona si usarlo en el coach.",
        );
      } catch (error) {
        toast(error.message, true);
        await loadLibrary();
      }
    });
    const preview = document.createElement("button");
    preview.type = "button";
    preview.className = "ghost";
    preview.textContent = "Ver muestra";
    preview.disabled = doc.active == null;
    preview.addEventListener("click", async () => {
      try {
        const result = await api("/api/library/" + doc.id + "/preview");
        $("library-preview-body").replaceChildren();
        for (const f of result.fragments) {
          const h = document.createElement("h3"),
            p = document.createElement("p");
          h.textContent = f.locator;
          p.textContent = f.text;
          $("library-preview-body").append(h, p);
        }
        $("library-preview").showModal();
      } catch (error) {
        toast(error.message, true);
      }
    });
    const versions = document.createElement("details"),
      caption = document.createElement("summary");
    caption.textContent = "Versiones y estado";
    versions.append(caption);
    for (const v of doc.versions) {
      const p = document.createElement("p");
      p.textContent =
        "v" +
        v.version +
        " · " +
        v.filename +
        " · " +
        ({
          pending: "Pendiente de procesamiento",
          ready: "Procesada",
          failed: "No se pudo procesar",
        }[v.status] || v.status) +
        " · " +
        v.chunks +
        " fragmentos · " +
        new Date(v.created).toLocaleString("es-ES") +
        (v.detail ? " · " + v.detail : "") +
        (v.warnings.length ? " · " + v.warnings.join(" ") : "");
      versions.append(p);
    }
    item.append(heading, by, label, process, preview, versions);
    $("library-documents").append(item);
  }
  if (data.documents.some((d) => d.id === selected))
    $("library-target").value = selected;
}
function init() {
  $("library-preview-close").addEventListener("click", () =>
    $("library-preview").close(),
  );
  $("library-target").addEventListener("change", () => {
    const replacing = Boolean($("library-target").value);
    $("library-title").disabled = replacing;
    $("library-author").disabled = replacing;
    $("library-upload").textContent = replacing
      ? "Subir actualización"
      : "Subir archivo";
  });
  $("library-upload-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = $("library-upload");
    button.disabled = true;
    try {
      const file = $("library-file").files[0];
      if (!file || file.size > 40 * 1024 * 1024)
        throw new Error("Selecciona un documento de hasta 40 MB.");
      const query = new URLSearchParams({
        filename: file.name,
        title: $("library-title").value,
        author: $("library-author").value,
      });
      if ($("library-target").value)
        query.set("document_id", $("library-target").value);
      const response = await fetch("/api/library/upload?" + query, {
        method: "POST",
        headers: {
          "Content-Type": "application/octet-stream",
          "X-CSRF-Token": session.csrf,
        },
        body: file,
      });
      const data = await response.json();
      if (!response.ok)
        throw new Error(data.detail || "No se pudo subir el documento.");
      $("library-file").value = "";
      await loadLibrary();
      toast(
        "Archivo guardado. Pulsa Procesar documento para incorporarlo; todavía no se usa en el coach.",
      );
    } catch (error) {
      toast(error.message, true);
    } finally {
      button.disabled = false;
    }
  });
}

export { init, renderSourceAudit, loadLibrary };
