"""Rutas de pro."""

from datetime import UTC, datetime

import httpx2 as httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from garmin_planner.api.schemas import ModelBody, ProStartBody
from garmin_planner.api.security import COOKIE
from garmin_planner.pro import ProError


def build_router(app, config, authenticated, session, set_cookie):
    router = APIRouter()

    @router.post("/api/pro/start", dependencies=[Depends(authenticated)])
    def pro_start(body: ProStartBody, request: Request):
        return {"url": app.state.pro.start(request.cookies[COOKIE], body.new_account)}

    @router.get("/auth/callback")
    def pro_callback(request: Request, record=Depends(authenticated)):
        try:
            app.state.pro.complete(request.cookies[COOKIE], dict(request.query_params))
            notice = "Cuenta ChatGPT conectada. Comprueba los permisos en Conexiones."
        except (ProError, httpx.HTTPError, KeyError, ValueError):
            notice = "OpenAI no completó la autorización. Reintenta desde Conexiones."
        app.state.store.set("pro_notice", notice)
        return RedirectResponse("/#connections", status_code=303)

    @router.get("/api/pro/notice", dependencies=[Depends(authenticated)])
    def pro_notice():
        return {"message": app.state.store.get("pro_notice")}

    @router.get("/api/pro/models", dependencies=[Depends(authenticated)])
    def pro_models():
        return {"models": app.state.pro.models()}

    @router.post("/api/pro/test", dependencies=[Depends(authenticated)])
    def pro_test(body: ModelBody):
        def work(job):
            result = app.state.pro.test(body.model)
            app.state.store.set(
                "pro_test",
                {
                    "at": datetime.now(UTC).isoformat(),
                    "model": body.model,
                    "usage": result["usage"],
                },
            )
            return result

        return {"job_id": app.state.jobs.start("pro", work)}

    @router.post("/api/pro/disconnect", dependencies=[Depends(authenticated)])
    def disconnect_pro():
        return {"job_id": app.state.jobs.start("pro", lambda job: app.state.pro.disconnect())}

    return router
