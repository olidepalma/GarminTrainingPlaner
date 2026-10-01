import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from garmin_planner.app import create_app
from garmin_planner.coach import Accept, Coach, Generate, Plan, Setup, context, validate_plan
from garmin_planner.config import Settings
from garmin_planner.pro import ProError
from garmin_planner.storage import Store


def setup(today):
    return Setup.model_validate(
        {
            "profile": {
                "availability": [90] * 7,
                "max_days": 5,
                "initial_model": "initial",
                "weekly_model": "weekly",
                "strength": True,
            },
            "events": [
                {
                    "name": "Sprint",
                    "day": str(today + timedelta(days=90)),
                    "sport": "triathlon",
                    "priority": "primary",
                    "distances": "750m / 20km / 5km",
                },
                {
                    "name": "10 km",
                    "day": str(today + timedelta(days=30)),
                    "sport": "running",
                    "priority": "secondary",
                },
            ],
        }
    ).model_dump(mode="json")


def plan(today):
    return Plan.model_validate(
        {
            "strategy": "Base y puesta a punto hasta el sprint; 10 km como preparación.",
            "rationale": "Sesiones suaves de inicio.",
            "sessions": [
                {
                    "day": str(today),
                    "sport": "cycling",
                    "title": "Bici de transición",
                    "minutes": 45,
                    "intensity": "easy",
                    "instructions": "Bici suave antes de carrera.",
                },
                {
                    "day": str(today),
                    "sport": "running",
                    "title": "Transición",
                    "minutes": 15,
                    "intensity": "easy",
                    "instructions": "Carrera después de bici.",
                },
                {
                    "day": str(today + timedelta(days=1)),
                    "sport": "swimming",
                    "title": "Técnica",
                    "minutes": 30,
                    "intensity": "easy",
                    "instructions": "Técnica suave.",
                },
            ],
        }
    )


class FakePro:
    def __init__(self, result):
        self.result, self.calls = result, []

    def respond(self, model, prompt, instructions=None):
        self.calls.append((model, prompt))
        return {"text": self.result.model_dump_json(), "usage": {"input_tokens": 500}}


def test_generation_memory_and_acceptance(tmp_path):
    today = date.today()
    store = Store(tmp_path)
    store.set("coach_setup", setup(today))
    pro = FakePro(plan(today))
    coach = Coach(store, pro, "Europe/Madrid")
    result = coach.generate(Generate(start=today, mode="initial"))
    assert pro.calls[0][0] == "initial"
    assert "10 km" in pro.calls[0][1]
    assert store.get("coach_calendar") is None
    coach.accept(Accept(draft_id=result["draft_id"], plan=plan(today)))
    assert len(store.get("coach_calendar")) == 3
    assert store.get("coach_draft") is None
    coach.generate(Generate(start=today, mode="weekly"))
    assert pro.calls[-1][0] == "weekly"
    assert "previous_decision" in pro.calls[-1][1]
    draft = store.get("coach_draft")
    coach.accept(Accept(draft_id=draft["id"], plan=plan(today)))
    assert len(store.get("coach_calendar")) == 3


def test_constraints_and_secondary_priorities():
    today = date.today()
    settings = setup(today)
    settings["events"][1]["priority"] = "primary"
    with pytest.raises(ValidationError):
        Setup.model_validate(settings)
    settings = setup(today)
    result = plan(today)
    result.sessions[0].minutes = 85
    with pytest.raises(ProError, match="disponibilidad"):
        validate_plan(result, settings, today)
    result = plan(today)
    result.sessions[0].day = today + timedelta(days=7)
    with pytest.raises(ProError, match="fuera"):
        validate_plan(result, settings, today)
    result = plan(today)
    result.sessions[0].sport = "strength"
    settings["profile"]["strength"] = False
    with pytest.raises(ProError, match="disciplina"):
        validate_plan(result, settings, today)


def test_stale_draft_rejected(tmp_path):
    today = date.today()
    store = Store(tmp_path)
    store.set("coach_setup", setup(today))
    coach = Coach(store, FakePro(plan(today)), "Europe/Madrid")
    draft = coach.generate(Generate(start=today, mode="initial"))
    changed = setup(today)
    changed["profile"]["availability"] = [10] * 7
    store.set("coach_setup", changed)
    with pytest.raises(ProError, match="perfil actual"):
        coach.accept(Accept(draft_id=draft["draft_id"], plan=plan(today)))
    assert store.get("coach_calendar") is None


def test_context_is_aggregated_and_wellness_opt_in(tmp_path):
    today = date.today()
    store = Store(tmp_path)
    store.save_activities(
        [
            {
                "id": str(i),
                "day": str(today),
                "sport": "running",
                "name": "PRIVATE ACTIVITY NAME",
                "duration_seconds": 60,
                "distance_m": 100,
            }
            for i in range(1000)
        ],
        {},
    )
    store.save_wellness(
        str(today),
        {
            "day": str(today),
            "resting_hr": 50,
            "sleep_score": 90,
            "hrv_ms": 60,
            "private": "PRIVATE",
        },
    )
    settings = setup(today)
    summary = context(store, settings, today, today)
    assert len(summary["recent_weeks"]) == 6
    assert "PRIVATE" not in json.dumps(summary)
    assert len(json.dumps(summary)) < 4000
    assert "wellness" not in summary
    settings["profile"]["use_wellness"] = True
    store.set("wellness_options", {"sleep": True, "hrv": False})
    summary = context(store, settings, today, today)
    assert summary["wellness"][0]["sleep_score"] == 90
    assert "hrv_ms" not in summary["wellness"][0]


def test_coach_endpoints_auth_and_csrf(tmp_path):
    app = create_app(Settings(_env_file=None, data_dir=tmp_path, auto_sync=False))
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        assert client.get("/api/coach").status_code == 401
        csrf = client.get("/api/session").json()["csrf"]
        login = client.post(
            "/api/session/login",
            json={"password": "test-coach-password"},
            headers={"Origin": "http://127.0.0.1:8000", "X-CSRF-Token": csrf},
        ).json()
        body = setup(date.today())
        assert client.post("/api/coach/setup", json=body).status_code == 403
        headers = {"Origin": "http://127.0.0.1:8000", "X-CSRF-Token": login["csrf"]}
        assert client.post("/api/coach/setup", json=body, headers=headers).status_code == 200
        assert client.get("/api/coach").json()["setup"]["events"][1]["priority"] == "secondary"
        assert (
            client.post(
                "/api/coach/accept",
                json={"draft_id": "missing", "plan": plan(date.today()).model_dump(mode="json")},
                headers=headers,
            ).status_code
            == 409
        )


def test_invalid_model_output_keeps_calendar_untouched(tmp_path):
    today = date.today()
    store = Store(tmp_path)
    store.set("coach_setup", setup(today))
    store.set("coach_calendar", [{"day": str(today), "title": "Manual"}])

    class InvalidPro:
        def respond(self, model, prompt, instructions=None):
            return {"text": "not JSON", "usage": {}}

    with pytest.raises(ProError, match="plan válido"):
        Coach(store, InvalidPro(), "Europe/Madrid").generate(Generate(start=today, mode="initial"))
    assert store.get("coach_calendar")[0]["title"] == "Manual"
    assert store.get("coach_draft") is None


def test_long_days_and_max_days_are_enforced():
    today = date.today()
    settings = setup(today)
    result = plan(today)
    settings["profile"]["long_bike_day"] = (today.weekday() + 1) % 7
    result.sessions[0].long_session = True
    with pytest.raises(ProError, match="día elegido"):
        validate_plan(result, settings, today)
    result.sessions[0].long_session = False
    settings["profile"]["max_days"] = 1
    with pytest.raises(ProError, match="disponibilidad"):
        validate_plan(result, settings, today)


def test_invalid_plan_fields_are_diagnosed_and_response_kept_locally(tmp_path):
    today = date.today()
    store = Store(tmp_path)
    store.set("coach_setup", setup(today))

    class WrongShape:
        def respond(self, model, prompt, instructions=None):
            assert '"maxLength": 6000' in instructions
            output = plan(today).model_dump(mode="json")
            output["strategy"] = ["PRIVATE OUTPUT"]
            return {"text": json.dumps(output), "usage": {}}

    with pytest.raises(ProError, match="strategy: debe ser texto") as exc:
        Coach(store, WrongShape(), "Europe/Madrid").generate(Generate(start=today, mode="initial"))
    assert "PRIVATE OUTPUT" not in str(exc.value)
    assert store.get("coach_last_failure")["issues"][0]["field"] == "strategy"
    assert store.get("coach_calendar") is None


def test_personal_profile_reaches_context_and_remains_optional(tmp_path):
    today = date.today()
    data = setup(today)
    assert data["profile"]["weight_kg"] is None
    data["profile"].update(
        sex="female",
        age=30,
        weight_kg=65.5,
        height_cm=168,
        strength_equipment="Mancuernas",
        strength_loads="Remo: 8 kg por mancuerna",
    )
    validated = Setup.model_validate(data).model_dump(mode="json")
    store = Store(tmp_path)
    store.set("coach_setup", validated)
    pro = FakePro(plan(today))
    Coach(store, pro, "Europe/Madrid").generate(Generate(start=today, mode="initial"))
    sent = json.loads(pro.calls[0][1])
    assert sent["setup"]["profile"]["weight_kg"] == 65.5
    assert sent["setup"]["profile"]["strength_loads"] == "Remo: 8 kg por mancuerna"
    data["profile"]["weight_kg"] = -1
    with pytest.raises(ValidationError):
        Setup.model_validate(data)


def test_strength_list_generation_and_missing_details(tmp_path):
    today = date.today()
    store = Store(tmp_path)
    store.set("coach_setup", setup(today))
    data = plan(today).model_dump(mode="json")
    strength = data["sessions"][0]
    strength.update(
        sport="strength",
        minutes=20,
        long_session=False,
        strength_exercises=[
            {
                "name": "Bird-dog",
                "sets": 2,
                "repetitions": "6-8 por lado",
                "load": "Sin carga externa",
                "rest_seconds": 45,
                "cues": "Mantén el tronco estable",
            }
        ],
    )
    result = Coach(store, FakePro(Plan.model_validate(data)), "Europe/Madrid").generate(
        Generate(start=today, mode="initial")
    )
    assert result["draft_id"]
    assert (
        store.get("coach_draft")["plan"]["sessions"][0]["strength_exercises"][0]["name"]
        == "Bird-dog"
    )
    data["sessions"][0]["strength_exercises"] = []
    with pytest.raises(ProError, match="ejercicios concretos"):
        Coach(store, FakePro(Plan.model_validate(data)), "Europe/Madrid").generate(
            Generate(start=today, mode="initial")
        )
