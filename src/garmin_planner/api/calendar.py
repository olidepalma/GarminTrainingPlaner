"""Rutas de calendar."""

from fastapi import APIRouter, Depends, Query

from garmin_planner.calendar import month_calendar


def build_router(app, config, authenticated, session, set_cookie):
    router = APIRouter()

    @router.get("/api/calendar", dependencies=[Depends(authenticated)])
    def calendar_month(year: int = Query(ge=2000, le=2100), month: int = Query(ge=1, le=12)):
        return month_calendar(app.state.store, year, month, app.state.workouts)

    return router
