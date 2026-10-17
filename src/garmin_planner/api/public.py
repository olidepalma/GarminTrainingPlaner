"""Rutas de public."""

import hashlib
from importlib.resources import files

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response

from garmin_planner import __version__


def build_router(app, config, authenticated, session, set_cookie):
    router = APIRouter()
    assets = files("garmin_planner").joinpath("static")
    stylesheet = assets.joinpath("style.css").read_bytes()
    style_digest = hashlib.sha256(stylesheet).hexdigest()[:16]
    style_url = f"/assets/style-{style_digest}.css"

    # Version the entire module graph: changing only app.js would leave its relative
    # imports on their old cache keys. Snapshot bytes so one URL always means one build.
    scripts = {"app.js": assets.joinpath("app.js").read_bytes()}
    scripts.update(
        {
            "modules/" + path.name: path.read_bytes()
            for path in assets.joinpath("modules").iterdir()
            if path.name.endswith(".js") and path.is_file()
        }
    )
    script_hash = hashlib.sha256()
    for name, content in sorted(scripts.items()):
        script_hash.update(name.encode() + b"\0" + content + b"\0")
    script_root = f"/assets/js-{script_hash.hexdigest()[:16]}"

    @router.get(script_root + "/{path:path}", include_in_schema=False)
    def versioned_script(path: str):
        if path not in scripts:
            raise HTTPException(404, "Archivo no encontrado.")
        return Response(scripts[path], media_type="text/javascript")

    @router.get(style_url, include_in_schema=False)
    def versioned_stylesheet():
        return Response(stylesheet, media_type="text/css")

    @router.get("/", response_class=HTMLResponse, include_in_schema=False)
    def home():
        return (
            assets.joinpath("index.html")
            .read_text(encoding="utf-8")
            .replace('href="/static/style.css"', f'href="{style_url}"')
            .replace('src="/static/app.js"', f'src="{script_root}/app.js"')
        )

    @router.get("/api/health")
    def health():
        return {
            "status": "ok",
            "version": __version__,
            "timezone": config.timezone,
            "mode": "https_proxy" if config.public_origin else "local_development",
        }

    return router
