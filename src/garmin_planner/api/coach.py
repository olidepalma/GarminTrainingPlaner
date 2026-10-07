"""Rutas de coach."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException

from garmin_planner.coach import Accept, Coach, Generate, Setup
from garmin_planner.review import Feedback, weekly_review


def build_router(app, config, authenticated, session, set_cookie):
    router = APIRouter()

    @router.get("/api/coach", dependencies=[Depends(authenticated)])
    def coach_state():
        return {
            key: app.state.store.get("coach_" + key)
            for key in ("setup", "draft", "accepted", "calendar")
        }

    @router.post("/api/coach/setup", dependencies=[Depends(authenticated)])
    def coach_setup(body: Setup):
        app.state.store.set("coach_setup", body.model_dump(mode="json"))
        return {"ok": True}

    @router.post("/api/coach/generate", dependencies=[Depends(authenticated)])
    def coach_generate(body: Generate):
        coach = Coach(app.state.store, app.state.pro, config.timezone, app.state.library)
        return {"job_id": app.state.jobs.start("pro", lambda job: coach.generate(body))}

    @router.post("/api/coach/accept", dependencies=[Depends(authenticated)])
    def coach_accept(body: Accept):
        return Coach(app.state.store, app.state.pro, config.timezone).accept(body)

    @router.get("/api/coach/review", dependencies=[Depends(authenticated)])
    def coach_review():
        return weekly_review(app.state.store, datetime.now(ZoneInfo(config.timezone)).date())

    @router.post("/api/coach/feedback", dependencies=[Depends(authenticated)])
    def coach_feedback(body: Feedback):
        today = datetime.now(ZoneInfo(config.timezone)).date()
        if body.week_start != today - timedelta(days=7):
            raise HTTPException(409, "La semana de revisión cambió. Actualiza la página.")
        data = app.state.store.get("coach_feedback", {})
        data[body.week_start.isoformat()] = body.model_dump(mode="json")
        app.state.store.set("coach_feedback", dict(sorted(data.items())[-52:]))
        return {"ok": True}

    @router.post("/api/coach/sessions/{source}/remove", dependencies=[Depends(authenticated)])
    def remove_coach_session(source: str, draft: bool = False):
        return app.state.workouts.remove_coach(source, draft)

    return router
