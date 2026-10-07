"""Rutas de public."""

from importlib.resources import files

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from garmin_planner import __version__


def build_router(app, config, authenticated, session, set_cookie):
    router = APIRouter()
    assets = files("garmin_planner").joinpath("static")

    @router.get("/", response_class=HTMLResponse, include_in_schema=False)
    def home():
        return assets.joinpath("index.html").read_text(encoding="utf-8")

    @router.get("/api/health")
    def health():
        return {
            "status": "ok",
            "version": __version__,
            "timezone": config.timezone,
            "mode": "https_proxy" if config.public_origin else "local_development",
        }

    return router
