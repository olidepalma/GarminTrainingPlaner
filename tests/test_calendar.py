from datetime import date

from test_coach import plan, setup

from garmin_planner.calendar import month_calendar
from garmin_planner.sports_data import extract_metrics
from garmin_planner.storage import Store


def test_garmin_prediction_field_names_and_alias_deduplication():
    raw = {
        "calendarDate": "2026-10-01",
        "time5K": 1200,
        "time10K": 2500,
        "timeHalfMarathon": 5500,
        "timeMarathon": 12000,
        "raceTime5K": 1200,
        "userProfilePK": "private",
    }
    rows = extract_metrics(raw, "predictions")
    assert len(rows) == 4
    assert {r["label"] for r in rows} == {"5 km", "10 km", "Media maratón", "Maratón"}
    assert all(r["measured_on"] == "2026-10-01" for r in rows)
    assert "private" not in str(rows)


def test_calendar_keeps_planned_and_completed_distinct(tmp_path):
    store = Store(tmp_path)
    today = date(2026, 10, 1)
    store.set("coach_setup", setup(today))
    store.set("coach_calendar", plan(today).model_dump(mode="json")["sessions"])
    store.save_activities(
        [
            {
                "id": "1",
                "day": "2026-10-01",
                "sport": "running",
                "name": "Run",
                "duration_seconds": 1800,
                "distance_m": 5000,
                "elevation_m": 10,
                "average_hr": 140,
            },
            {"id": "2", "day": "2026-09-30", "sport": "cycling", "name": "Old ride"},
        ],
        {},
    )
    response = month_calendar(store, 2026, 10)
    assert response["from"] == "2026-10-01"
    assert response["through"] == "2026-10-31"
    assert len([e for e in response["entries"] if e["kind"] == "completed"]) == 1
    assert len([e for e in response["entries"] if e["kind"] == "planned"]) == 3
    assert len([e for e in response["entries"] if e["kind"] == "race"]) == 1
    assert len({e["id"] for e in response["entries"]}) == len(response["entries"])
    assert (
        next(e for e in response["entries"] if e["kind"] == "completed")["detail"]["average_hr"]
        == 140
    )


def test_calendar_empty_and_leap_year(tmp_path):
    result = month_calendar(Store(tmp_path), 2028, 2)
    assert result["through"] == "2028-02-29"
    assert result["entries"] == []


def test_recent_vo2_not_lost_when_precise_and_rounded_records_fill_limit():
    rows = extract_metrics(
        [
            {
                "calendarDate": f"2026-10-{day:02}",
                "generic": {"vo2MaxValue": 50, "vo2MaxPreciseValue": 50 + day / 100},
                "cycling": {"vo2MaxValue": 52, "vo2MaxPreciseValue": 52 + day / 100},
            }
            for day in range(1, 32)
        ],
        "vo2",
    )
    assert rows[0]["measured_on"] == "2026-10-31"
    assert all(r["field"] == "vo2MaxPreciseValue" for r in rows)
    assert any(r["sport"] == "cycling" and r["measured_on"] == "2026-10-31" for r in rows)


def test_calendar_labels_current_draft_and_ignores_stale_draft(tmp_path):
    from garmin_planner.coach import fingerprint

    store = Store(tmp_path)
    today = date(2026, 10, 1)
    profile = setup(today)
    store.set("coach_setup", profile)
    store.set(
        "coach_draft",
        {"setup_hash": fingerprint(profile), "plan": plan(today).model_dump(mode="json")},
    )
    entries = month_calendar(store, 2026, 10)["entries"]
    assert len([e for e in entries if e.get("is_draft")]) == 3
    profile["profile"]["max_days"] = 4
    store.set("coach_setup", profile)
    entries = month_calendar(store, 2026, 10)["entries"]
    assert not any(e.get("is_draft") for e in entries)
