import copy
from datetime import date

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from garmin_planner.app import create_app
from garmin_planner.calendar import month_calendar
from garmin_planner.coach import Session
from garmin_planner.config import Settings
from garmin_planner.garmin import GarminError
from garmin_planner.storage import Store
from garmin_planner.workouts import (
    Workout,
    Workouts,
    duration_warnings,
    garmin_payload,
    session_key,
)


def workout():
    return Workout.model_validate(
        {
            "title": "Test blocks",
            "day": str(date.today()),
            "sport": "running",
            "minutes": 20,
            "structure": {
                "blocks": [
                    {"kind": "warmup", "value": 300},
                    {
                        "kind": "repeat",
                        "iterations": 5,
                        "steps": [
                            {"kind": "exercise", "value": 60, "target": "hr_zone", "zone": 2},
                            {"kind": "recovery", "value": 60},
                        ],
                    },
                    {"kind": "cooldown", "value": 300},
                ]
            },
        }
    )


class Remote:
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def upload_workout(self, payload):
        self.calls.append(("upload", copy.deepcopy(payload)))
        if self.fail == "upload":
            raise TimeoutError()
        return {"workoutId": 123}

    def schedule_workout(self, identifier, day):
        self.calls.append(("schedule", identifier, day))
        if self.fail == "schedule":
            raise TimeoutError()
        return {"id": 456}


class Garmin:
    def __init__(self, remote):
        self.remote = remote

    def workout_client(self):
        return self.remote


def test_repeats_units_targets_and_unique_step_order():
    payload = garmin_payload(workout())
    steps = payload["workoutSegments"][0]["workoutSteps"]
    assert steps[0]["endConditionValue"] == 300
    assert steps[1]["numberOfIterations"] == 5
    assert steps[1]["workoutSteps"][0]["zoneNumber"] == 2
    assert steps[1]["workoutSteps"][0]["targetType"]["workoutTargetTypeKey"] == "heart.rate.zone"
    assert [
        steps[0]["stepOrder"],
        steps[1]["stepOrder"],
        *[s["stepOrder"] for s in steps[1]["workoutSteps"]],
        steps[2]["stepOrder"],
    ] == [1, 2, 3, 4, 5]


def test_pool_stroke_equipment_and_unknown_equipment_preserved_in_notes():
    w = Workout.model_validate(
        {
            "title": "Swim",
            "day": str(date.today()),
            "sport": "swimming",
            "minutes": 30,
            "structure": {
                "pool_length": 25,
                "blocks": [
                    {
                        "kind": "exercise",
                        "duration_type": "distance",
                        "value": 200,
                        "stroke": "free",
                        "equipment": "kickboard",
                        "notes": "Technique",
                    }
                ],
            },
        }
    )
    payload = garmin_payload(w)
    step = payload["workoutSegments"][0]["workoutSteps"][0]
    assert payload["poolLength"] == 25
    assert step["strokeType"]["strokeTypeId"] == 6
    assert step["equipmentType"]["equipmentTypeId"] == 2
    w.structure.blocks[0].equipment = "fins"
    step = garmin_payload(w)["workoutSegments"][0]["workoutSteps"][0]
    assert "equipmentType" not in step
    assert "fins" in step["description"]


def test_invalid_duration_repeat_pool_and_targets_rejected():
    bad = workout().model_dump(mode="json")
    bad["minutes"] = 10
    mismatch = Workout.model_validate(bad)
    assert duration_warnings(mismatch.structure, mismatch.minutes)
    bad["minutes"] = 40
    mismatch = Workout.model_validate(bad)
    assert duration_warnings(mismatch.structure, mismatch.minutes)
    assert not duration_warnings(workout().structure, workout().minutes)
    bad = workout().model_dump(mode="json")
    bad["structure"]["blocks"][1]["iterations"] = 1
    with pytest.raises(ValidationError, match="repeticiones"):
        Workout.model_validate(bad)
    bad = workout().model_dump(mode="json")
    bad["structure"]["blocks"][0].update(target="hr_zone", zone=7)
    with pytest.raises(ValidationError, match="cardiaca"):
        Workout.model_validate(bad)
    bad = {
        "title": "Pool",
        "day": str(date.today()),
        "sport": "swimming",
        "minutes": 20,
        "structure": {"pool_length": 25, "blocks": [{"duration_type": "distance", "value": 123}]},
    }
    with pytest.raises(ValidationError, match="múltiplo"):
        Workout.model_validate(bad)


def test_explicit_send_and_duplicate_protection(tmp_path):
    remote = Remote()
    store = Store(tmp_path)
    service = Workouts(store, Garmin(remote))
    identifier = service.save(workout())["id"]
    preview = service.preview(identifier)
    assert remote.calls == []
    result = service.send(identifier, preview["revision"])
    assert result["status"] == "complete"
    assert [c[0] for c in remote.calls] == ["upload", "schedule"]
    assert service.send(identifier, service.preview(identifier)["revision"])["already_sent"]
    assert len(remote.calls) == 2
    with pytest.raises(GarminError, match="variante"):
        service.save(workout(), identifier)


@pytest.mark.parametrize(
    "failure, status", [("upload", "uncertain"), ("schedule", "schedule_uncertain")]
)
def test_uncertain_writes_are_not_retried(tmp_path, failure, status):
    remote = Remote(failure)
    service = Workouts(Store(tmp_path), Garmin(remote))
    identifier = service.save(workout())["id"]
    with pytest.raises(GarminError):
        service.send(identifier, service.preview(identifier)["revision"])
    assert service.get(identifier)["publication"]["status"] == status
    count = len(remote.calls)
    with pytest.raises(GarminError):
        service.send(identifier, service.preview(identifier)["revision"])
    assert len(remote.calls) == count


def test_calendar_coach_and_manual_coexist_without_export_duplicate(tmp_path):
    store = Store(tmp_path)
    remote = Remote()
    service = Workouts(store, Garmin(remote))
    w = workout()
    manual = service.save(w)["id"]
    session = Session.model_validate(
        {
            "day": str(w.day),
            "sport": w.sport,
            "title": "Coach",
            "minutes": 20,
            "intensity": "easy",
            "instructions": "Easy",
            "workout": w.structure.model_dump(mode="json"),
        }
    ).model_dump(mode="json")
    store.set("coach_calendar", [session])
    exported = service.from_coach(session_key(session))["id"]
    assert exported != manual
    assert service.from_coach(session_key(session))["id"] == exported
    calendar = month_calendar(store, w.day.year, w.day.month, service)
    assert len(calendar["entries"]) == 2
    assert {entry["origin"] for entry in calendar["entries"]} == {"manual", "coach"}


def test_stale_preview_and_edits_while_authenticating_are_rejected(tmp_path):
    store = Store(tmp_path)
    remote = Remote()
    service = Workouts(store, Garmin(remote))
    identifier = service.save(workout())["id"]
    preview = service.preview(identifier)
    modified = workout()
    modified.title = "Modified"
    service.save(modified, identifier)
    with pytest.raises(GarminError, match="cambió"):
        service.send(identifier, preview["revision"])
    assert remote.calls == []


def test_private_routes_csrf_and_local_save(tmp_path):
    app = create_app(Settings(_env_file=None, data_dir=tmp_path, auto_sync=False))
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        assert client.get("/api/workout-options").status_code == 401
        csrf = client.get("/api/session").json()["csrf"]
        auth = client.post(
            "/api/session/login",
            json={"password": "test-workout-password"},
            headers={"Origin": "http://127.0.0.1:8000", "X-CSRF-Token": csrf},
        ).json()
        headers = {"Origin": "http://127.0.0.1:8000", "X-CSRF-Token": auth["csrf"]}
        body = workout().model_dump(mode="json")
        assert client.post("/api/workouts", json=body).status_code == 403
        identifier = client.post("/api/workouts", json=body, headers=headers).json()["id"]
        assert client.get(f"/api/workouts/{identifier}/preview").status_code == 200
        assert client.post(f"/api/workouts/{identifier}/remove", json={}).status_code == 403
        assert client.get("/api/workout-options").json()["strength_categories"]
        assert client.post("/api/workouts/validate", json=body, headers=headers).status_code == 200
        assert (
            client.get(
                "/api/calendar", params={"year": date.today().year, "month": date.today().month}
            ).json()["entries"][0]["origin"]
            == "manual"
        )
        assert (
            client.post(f"/api/workouts/{identifier}/remove", json={}, headers=headers).status_code
            == 200
        )
        assert not client.get(
            "/api/calendar", params={"year": date.today().year, "month": date.today().month}
        ).json()["entries"]


def test_upgrade_workout_table_without_source(tmp_path):
    store = Store(tmp_path)
    with store.connect() as db:
        db.execute(
            "CREATE TABLE workouts (id TEXT PRIMARY KEY, day TEXT NOT NULL, "
            "payload TEXT NOT NULL, publication TEXT NOT NULL DEFAULT '{}')"
        )
    service = Workouts(store, None)
    service.save(workout())
    assert len(service.list(str(date.today()), str(date.today()))) == 1


def test_duration_warning_keeps_estimate_and_step_seconds(tmp_path):
    body = workout().model_dump(mode="json")
    body["minutes"] = 30
    body["structure"]["blocks"][0]["value"] = 330
    model = Workout.model_validate(body)
    service = Workouts(Store(tmp_path), None)
    saved = service.save(model)
    assert saved["warnings"]
    preview = service.preview(saved["id"])
    assert "20:30" in preview["warnings"][0]
    assert preview["payload"]["estimatedDurationInSecs"] == 1800
    assert preview["payload"]["workoutSegments"][0]["workoutSteps"][0]["endConditionValue"] == 330


def test_remove_manual_preserves_remote_audit_and_excludes_calendar(tmp_path):
    store = Store(tmp_path)
    remote = Remote()
    service = Workouts(store, Garmin(remote))
    identifier = service.save(workout())["id"]
    service.send(identifier, service.preview(identifier)["revision"])
    calls = list(remote.calls)
    service.remove(identifier)
    assert service.list(str(date.today()), str(date.today())) == []
    with pytest.raises(GarminError):
        service.get(identifier)
    assert remote.calls == calls
    with store.connect() as db:
        row = db.execute(
            "SELECT deleted,publication FROM workouts WHERE id=?", (identifier,)
        ).fetchone()
        assert row["deleted"] == 1
        assert "workout_id" in row["publication"]


def test_remove_pending_send_rejected(tmp_path):
    service = Workouts(Store(tmp_path), None)
    identifier = service.save(workout())["id"]
    service._publication(identifier, {"status": "uncertain"})
    with pytest.raises(GarminError, match="incierto"):
        service.remove(identifier)
    assert service.get(identifier)


def test_remove_coach_and_draft_preserves_history(tmp_path):
    store = Store(tmp_path)
    service = Workouts(store, None)
    session = {"title": "Run", "day": str(date.today()), "sport": "running", "minutes": 20}
    store.set("coach_calendar", [session])
    store.set("coach_accepted", {"plan": {"sessions": [session]}})
    store.set("coach_draft", {"plan": {"sessions": [session]}, "warnings": []})
    service.remove_coach(session_key(session))
    assert store.get("coach_calendar") == []
    assert store.get("coach_accepted")["plan"]["sessions"] == [session]
    assert store.get("coach_draft")["plan"]["sessions"] == [session]
    service.remove_coach(session_key(session), draft=True)
    assert store.get("coach_draft")["plan"]["sessions"] == []
    assert len(store.get("removed_coach_sessions")) == 2
    with pytest.raises(GarminError):
        service.remove_coach(session_key(session))
