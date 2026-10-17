"""Rutas de calendar."""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, StrictBool

from garmin_planner.calendar import month_calendar


class CompletionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    completed: StrictBool


def build_router(app, config, authenticated, session, set_cookie):
    router = APIRouter()

    @router.get("/api/calendar", dependencies=[Depends(authenticated)])
    def calendar_month(year: int = Query(ge=2000, le=2100), month: int = Query(ge=1, le=12)):
        return month_calendar(app.state.store, year, month, app.state.workouts)

    @router.post("/api/calendar/{entry_id}/completion", dependencies=[Depends(authenticated)])
    def mark_completion(entry_id: str, body: CompletionBody):
        store = app.state.store
        # Resolve the server-owned session; never trust submitted duration or sport.
        if entry_id.startswith("planned-"):
            item = next(
                (s for s in store.planned_sessions() if "planned-" + s["id"] == entry_id), None
            )
            session = item["session"] if item else None
        elif entry_id.startswith("manual-"):
            with store.connect() as db:
                row = db.execute(
                    "SELECT id FROM workouts WHERE id=? AND deleted=0 AND source IS NULL",
                    (entry_id.removeprefix("manual-"),),
                ).fetchone()
            session = app.state.workouts.get(row["id"]) if row else None
        else:
            session = None
        if session is None and not body.completed:
            session = next(
                (
                    c
                    for c in store.completions("2000-01-01", "2100-12-31")
                    if c["entry_id"] == entry_id
                ),
                None,
            )
        if session is None:
            raise HTTPException(404, "Sesión planificada no encontrada.")
        today = datetime.now(ZoneInfo(config.timezone)).date().isoformat()
        if body.completed and session["day"] > today:
            raise HTTPException(400, "No puedes marcar una sesión futura como realizada.")
        snapshot = {k: session[k] for k in ("day", "sport", "title", "minutes")}
        store.set_completion(entry_id, snapshot, body.completed)
        return {"completed": body.completed}

    return router
