from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from test_coach import context, plan, setup

from garmin_planner.app import create_app
from garmin_planner.calendar import month_calendar
from garmin_planner.config import Settings
from garmin_planner.review import totals, weekly_review
from garmin_planner.storage import Store
from garmin_planner.workouts import Workout


def test_confirmed_session_counts_once_and_is_reversible(tmp_path):
    store = Store(tmp_path)
    day = date(2026, 10, 5)
    session = plan(day).model_dump(mode="json")["sessions"][0]
    session.update(sport="strength", title="Fuerza", minutes=40)
    store.set("coach_calendar", [session])
    entry = month_calendar(store, 2026, 10)["entries"][0]
    for _ in range(2):
        store.set_completion(entry["id"], session, True)
    assert month_calendar(store, 2026, 10)["entries"][0]["manual_completion"]
    assert totals(store, day, day)["strength"]["minutes"] == 40
    review = weekly_review(store, day + timedelta(days=1))
    assert review["sports"]["strength"]["actual"]["sessions"] == 1
    summary = context(store, setup(day), day + timedelta(days=7), day + timedelta(days=1))
    assert summary["manual_completions"][0]["title"] == "Fuerza"
    assert summary["recent_weeks"][str(day - timedelta(days=5))]["strength"]["minutes"] == 40
    # The actual report survives later changes to the proposed plan.
    store.set("coach_calendar", [])
    assert totals(store, day, day)["strength"]["minutes"] == 40
    assert month_calendar(store, 2026, 10)["entries"][0]["manual_completion"]
    store.set_completion(entry["id"], session, False)
    assert not totals(store, day, day)


def test_completion_api_rejects_drafts_future_sessions_and_requires_csrf(tmp_path):
    app = create_app(Settings(_env_file=None, data_dir=tmp_path, auto_sync=False))
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        store = app.state.store
        today = datetime.now(UTC).date()
        session = plan(today - timedelta(days=2)).model_dump(mode="json")["sessions"][0]
        store.set("coach_calendar", [session])
        entry_id = "planned-" + store.planned_sessions()[0]["id"]
        url = f"/api/calendar/{entry_id}/completion"
        assert client.post(url, json={"completed": True}).status_code in (401, 403)
        csrf = client.get("/api/session").json()["csrf"]
        login = client.post(
            "/api/session/login",
            json={"password": "test-coach-password"},
            headers={"Origin": "http://127.0.0.1:8000", "X-CSRF-Token": csrf},
        ).json()
        headers = {"Origin": "http://127.0.0.1:8000", "X-CSRF-Token": login["csrf"]}
        assert client.post(url, json={"completed": True}).status_code == 403
        for _ in range(2):
            assert client.post(url, json={"completed": True}, headers=headers).status_code == 200
        assert len(store.completions("2000-01-01", "2100-01-01")) == 1
        assert client.post(url, json={"completed": "false"}, headers=headers).status_code == 422
        store.set("coach_calendar", [])
        # An archived/replaced proposal keeps its completion visible and reversible.
        archived = month_calendar(store, today.year, today.month, app.state.workouts)
        assert any(e["id"] == entry_id and e["manual_completion"] for e in archived["entries"])
        assert client.post(url, json={"completed": False}, headers=headers).status_code == 200
        for invalid in ("draft-123", "garmin-123", "race-123", "planned-missing"):
            assert (
                client.post(
                    f"/api/calendar/{invalid}/completion", json={"completed": True}, headers=headers
                ).status_code
                == 404
            )
        workout = app.state.workouts.save(
            Workout.model_validate(
                {
                    "day": str(today - timedelta(days=1)),
                    "sport": "strength",
                    "title": "Gimnasio",
                    "minutes": 30,
                    "structure": {
                        "blocks": [{"kind": "exercise", "duration_type": "time", "value": 1800}]
                    },
                }
            )
        )
        manual_url = f"/api/calendar/manual-{workout['id']}/completion"
        assert client.post(manual_url, json={"completed": True}, headers=headers).status_code == 200
        session["day"] = str(today + timedelta(days=2))
        store.set("coach_calendar", [session])
        future_id = "planned-" + store.planned_sessions()[0]["id"]
        assert (
            client.post(
                f"/api/calendar/{future_id}/completion", json={"completed": True}, headers=headers
            ).status_code
            == 400
        )
