"""Rutas de workouts."""

from fastapi import APIRouter, Depends

from garmin_planner.api.schemas import CoachWorkoutBody, SendWorkoutBody
from garmin_planner.workouts import Workout


def build_router(app, config, authenticated, session, set_cookie):
    router = APIRouter()

    @router.post("/api/workouts", dependencies=[Depends(authenticated)])
    def create_workout(body: Workout):
        return app.state.workouts.save(body)

    @router.post("/api/workouts/validate", dependencies=[Depends(authenticated)])
    def validate_workout(body: Workout):
        return {"ok": True}

    @router.post("/api/workouts/from-coach", dependencies=[Depends(authenticated)])
    def import_coach_workout(body: CoachWorkoutBody):
        return app.state.workouts.from_coach(body.source)

    @router.post("/api/workouts/{identifier}/remove", dependencies=[Depends(authenticated)])
    def remove_workout(identifier: str):
        return app.state.workouts.remove(identifier)

    @router.post("/api/workouts/{identifier}", dependencies=[Depends(authenticated)])
    def edit_workout(identifier: str, body: Workout):
        app.state.workouts.get(identifier)
        return app.state.workouts.save(body, identifier)

    @router.get("/api/workouts/{identifier}", dependencies=[Depends(authenticated)])
    def get_workout(identifier: str):
        return app.state.workouts.get(identifier)

    @router.get("/api/workouts/{identifier}/preview", dependencies=[Depends(authenticated)])
    def preview_workout(identifier: str):
        return app.state.workouts.preview(identifier)

    @router.post("/api/workouts/{identifier}/send", dependencies=[Depends(authenticated)])
    def send_workout(identifier: str, body: SendWorkoutBody):
        app.state.workouts.get(identifier)
        return {
            "job_id": app.state.jobs.start(
                "garmin", lambda job: app.state.workouts.send(identifier, body.revision)
            )
        }

    @router.get("/api/workout-options", dependencies=[Depends(authenticated)])
    def workout_options():
        from garminconnect.exercises import CATEGORIES

        return {
            "strength_categories": sorted(CATEGORIES),
            "catalog": app.state.store.get("garmin_workout_catalog", {}),
        }

    return router
