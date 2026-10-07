"""Rutas de public."""

import hashlib
from importlib.resources import files

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response

from garmin_planner import __version__


def build_router(app, config, authenticated, session, set_cookie):
    router = APIRouter()
    assets = files("garmin_planner").joinpath("static")
    stylesheet = assets.joinpath("style.css").read_bytes()
    style_digest = hashlib.sha256(stylesheet).hexdigest()[:16]
    style_url = f"/assets/style-{style_digest}.css"

    @router.get(style_url, include_in_schema=False)
    def versioned_stylesheet():
        return Response(stylesheet, media_type="text/css")

    @router.get("/", response_class=HTMLResponse, include_in_schema=False)
    def home():
        return (
            assets.joinpath("index.html")
            .read_text(encoding="utf-8")
            .replace('href="/static/style.css"', f'href="{style_url}"')
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
