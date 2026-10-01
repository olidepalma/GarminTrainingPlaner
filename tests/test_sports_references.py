from datetime import date

import pytest
from pydantic import ValidationError
from test_coach import plan, setup

from garmin_planner.coach import Event, Profile, context, validate_plan
from garmin_planner.pro import ProError
from garmin_planner.sports_data import extract_metrics, sync_references
from garmin_planner.storage import Store


def test_distance_catalog_resolves_on_server():
    event = Event(
        name="Sprint",
        day=date.today(),
        sport="triathlon",
        priority="primary",
        distance_code="sprint",
        distances="wrong",
    )
    assert event.distances == "Natación 750 m / bici 20 km / carrera 5 km"
    event = Event(
        name="Media", day=date.today(), sport="running", priority="secondary", distance_code="half"
    )
    assert event.distances == "21.0975 km"
    with pytest.raises(ValidationError):
        Event(
            name="Invalid",
            day=date.today(),
            sport="running",
            priority="primary",
            distance_code="sprint",
        )
    event = Event(
        name="Trail",
        day=date.today(),
        sport="trail",
        priority="secondary",
        distances="37 km, 2000 m D+",
    )
    assert event.distances == "37 km, 2000 m D+"


def test_slots_keep_morning_and_afternoon_separate():
    today = date.today()
    settings = setup(today)
    settings["profile"]["availability"] = [120] * 7
    settings["profile"]["slots"] = [
        [{"period": "morning", "minutes": 60}, {"period": "afternoon", "minutes": 60}]
        for _ in range(7)
    ]
    result = plan(today)
    for session in result.sessions:
        session.slot = 0
    validate_plan(result, settings, today)  # bici + carrera continua de 60 minutos
    result.sessions[0].minutes = 70
    with pytest.raises(ProError, match="franja"):
        validate_plan(result, settings, today)
    result.sessions[0].minutes = 45
    result.sessions[0].slot = 2
    with pytest.raises(ProError, match="franja disponible"):
        validate_plan(result, settings, today)
    settings["profile"]["availability"][0] = 100
    with pytest.raises(ValidationError, match="suma"):
        Profile.model_validate(settings["profile"])


def test_extracts_only_sports_fields_and_keeps_profile_and_date():
    rows = extract_metrics(
        [
            {
                "sport": "RUNNING",
                "zone1Floor": 100,
                "maxHeartRate": 190,
                "userProfilePK": "private",
                "email": "private@example.test",
                "calendarDate": "2026-10-01",
            }
        ],
        "hr_zones",
    )
    assert rows[0]["sport"] == "RUNNING"
    assert rows[0]["measured_on"] == "2026-10-01"
    assert "private" not in str(rows)
    assert (
        extract_metrics({"raceTime5K": 1200, "raceTime10K": None}, "predictions")[0]["unit"] == "s"
    )
    assert extract_metrics({"functionalThresholdPower": float("nan")}, "ftp") == []
    assert (
        extract_metrics({"speed": 350, "heartRate": 160}, "threshold")[0]["label"]
        == "FC umbral de carrera"
    )


def test_sync_partial_failures_preserve_previous_and_report_status(tmp_path):
    store = Store(tmp_path)
    store.set(
        "garmin_references",
        {"groups": {"ftp": {"rows": [{"value": 220}], "at": "previous", "status": "available"}}},
    )

    class Client:
        def get_heart_rate_zones(self):
            return [{"sport": "CYCLING", "zone1Floor": 100}]

        def get_cycling_ftp(self):
            raise RuntimeError("sensitive error")

    warnings = sync_references(Client(), store, date.today())
    data = store.get("garmin_references")
    assert warnings
    assert data["groups"]["ftp"]["rows"][0]["value"] == 220
    assert data["groups"]["ftp"]["status"] == "failed"
    assert data["groups"]["ftp"]["at"] == "previous"
    assert data["groups"]["hr_zones"]["status"] == "available"
    assert "sensitive" not in str(data)


def test_coach_uses_garmin_references_with_opt_out(tmp_path):
    store = Store(tmp_path)
    store.set(
        "garmin_references",
        {
            "groups": {
                "ftp": {"rows": [{"value": 250}], "status": "available", "at": "today"},
                "predictions": {"rows": [{"value": 1200}]},
            }
        },
    )
    settings = setup(date.today())
    payload = context(store, settings, date.today(), date.today())
    assert payload["garmin_references"]["ftp"]["rows"][0]["value"] == 250
    assert payload["garmin_references"]["predictions"]["rows"][0]["value"] == 1200
    settings["profile"]["use_garmin_zones"] = False
    payload = context(store, settings, date.today(), date.today())
    assert "garmin_references" not in payload
