"""Registro explícito de routers del servidor."""

from garmin_planner.api.auth import build_router as auth_router
from garmin_planner.api.calendar import build_router as calendar_router
from garmin_planner.api.coach import build_router as coach_router
from garmin_planner.api.garmin import build_router as garmin_router
from garmin_planner.api.jobs import build_router as jobs_router
from garmin_planner.api.library import build_router as library_router
from garmin_planner.api.pro import build_router as pro_router
from garmin_planner.api.public import build_router as public_router
from garmin_planner.api.workouts import build_router as workouts_router

ROUTERS = (
    public_router,
    auth_router,
    garmin_router,
    jobs_router,
    pro_router,
    calendar_router,
    coach_router,
    library_router,
    workouts_router,
)
