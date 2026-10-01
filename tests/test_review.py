from datetime import date, timedelta

from garmin_planner.review import weekly_review
from garmin_planner.storage import Store


def test_comparison_and_sport_trend_exclude_today(tmp_path):
    store = Store(tmp_path)
    today = date(2026, 10, 1)
    yesterday = str(today - timedelta(days=1))
    rows = [
        {
            "id": "run",
            "day": yesterday,
            "sport": "running",
            "duration_seconds": 3600,
            "distance_m": 10000,
        },
        {
            "id": "bike",
            "day": yesterday,
            "sport": "cycling",
            "duration_seconds": 7200,
            "distance_m": 50000,
        },
        {"id": "today", "day": str(today), "sport": "running", "duration_seconds": 3600},
        {
            "id": "baseline",
            "day": str(today - timedelta(days=8)),
            "sport": "running",
            "duration_seconds": 1800,
            "distance_m": 5000,
        },
    ]
    store.save_activities(rows, {"at": "last_sync"})
    store.set("coach_calendar", [{"day": yesterday, "sport": "running", "minutes": 45}])
    report = weekly_review(store, today)
    run = report["sports"]["running"]
    assert run["planned"]["minutes"] == 45
    assert run["actual"]["minutes"] == 60
    assert run["volume_change_percent"] == 100
    assert run["prior_active_weeks"] == 1
    assert report["sports"]["cycling"]["volume_change_percent"] is None
    assert report["last_activity_sync"]["at"] == "last_sync"
    assert "TSS" in report["limitations"]
