"""Rutas de jobs."""

from fastapi import APIRouter, Depends, HTTPException

from garmin_planner.api.schemas import MFABody


def build_router(app, config, authenticated, session, set_cookie):
    router = APIRouter()

    @router.post("/api/jobs/{identifier}/mfa", dependencies=[Depends(authenticated)])
    def submit_mfa(identifier: str, body: MFABody):
        app.state.jobs.submit_mfa(identifier, body.code)
        return {"ok": True}

    @router.get("/api/jobs/{identifier}", dependencies=[Depends(authenticated)])
    def job_status(identifier: str):
        item = app.state.jobs.get(identifier)
        if not item:
            raise HTTPException(404, "Trabajo no encontrado; puede haberse reiniciado el servidor.")
        return item

    return router
