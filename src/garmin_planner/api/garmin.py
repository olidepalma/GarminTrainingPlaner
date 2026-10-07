"""Rutas de garmin."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from garmin_planner.api.schemas import GarminBody, OptionsBody
from garmin_planner.garmin import GarminError, dashboard
from garmin_planner.sports_data import DISTANCES


def build_router(app, config, authenticated, session, set_cookie):
    router = APIRouter()

    @router.get("/api/connections", dependencies=[Depends(authenticated)])
    def connections():
        return {
            "garmin": app.state.garmin.status(),
            "pro": app.state.pro.status(),
            "nightly": {
                "hour": config.sync_hour,
                "timezone": config.timezone,
                "enabled": config.auto_sync,
            },
        }

    @router.get("/api/dashboard", dependencies=[Depends(authenticated)])
    def get_dashboard(
        days: int = Query(default=28, ge=7, le=365),
        sport: Literal["running", "trail", "cycling", "swimming", "strength", "triathlon", "other"]
        | None = None,
    ):
        return dashboard(app.state.store, config.timezone, days, sport)

    @router.post("/api/wellness-options", dependencies=[Depends(authenticated)])
    def wellness_options(body: OptionsBody):
        app.state.store.set("wellness_options", body.model_dump())
        return {"ok": True}

    @router.post("/api/garmin/connect", dependencies=[Depends(authenticated)])
    def garmin_connect(body: GarminBody):
        password = body.password.get_secret_value()
        if not 1 <= len(password) <= 1024:
            raise HTTPException(422, "Introduce tu contraseña Garmin.")
        identifier = app.state.jobs.start(
            "garmin",
            lambda job: app.state.garmin.connect(
                body.email, password, lambda: app.state.jobs.prompt_mfa(job)
            ),
        )
        return {"job_id": identifier}

    @router.post("/api/garmin/sync", dependencies=[Depends(authenticated)])
    def sync():
        if not app.state.vault.read("garmin"):
            raise GarminError("Conecta primero Garmin.")
        return {"job_id": app.state.start_sync()}

    @router.post("/api/garmin/disconnect", dependencies=[Depends(authenticated)])
    def disconnect_garmin():
        def disconnect(job):
            app.state.vault.delete("garmin")
            return {"ok": True}

        return {"job_id": app.state.jobs.start("garmin", disconnect)}

    @router.get("/api/sports-statistics", dependencies=[Depends(authenticated)])
    def sports_statistics():
        return app.state.store.get("garmin_references", {"groups": {}})

    @router.get("/api/race-distances", dependencies=[Depends(authenticated)])
    def race_distances():
        return {"catalog": DISTANCES}

    return router
