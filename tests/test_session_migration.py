import json
import sqlite3
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from test_coach import plan, setup

from garmin_planner.app import create_app
from garmin_planner.calendar import month_calendar
from garmin_planner.config import Settings
from garmin_planner.storage import Store
from garmin_planner.workouts import session_key


def legacy_database(root, calendar, draft):
    root.mkdir(exist_ok=True)
    with sqlite3.connect(root / "planner.sqlite3") as db:
        db.execute("CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
        db.executemany(
            "INSERT INTO meta VALUES(?,?)",
            [("coach_calendar", json.dumps(calendar)), ("coach_draft", json.dumps(draft))],
        )


def test_legacy_migration_is_lossless_and_repeatable(tmp_path):
    sessions = plan(date.today()).model_dump(mode="json")["sessions"]
    sessions[0]["workout"] = {"blocks": [{"kind": "exercise", "value": 600}]}
    sessions[0]["strength_exercises"] = [{"name": "Example", "load": "No external weight"}]
    draft = {
        "id": "draft-example",
        "setup_hash": "hash",
        "plan": {"sessions": sessions, "strategy": "Example"},
        "sources_snapshot": [{"id": "book-excerpt", "text": "text"}],
    }
    legacy_database(tmp_path, sessions, draft)
    (tmp_path / "secrets").mkdir()
    secret = tmp_path / "secrets" / "pro.enc"
    secret.write_bytes(b"unchanged-encrypted-credentials")
    store = Store(tmp_path)
    assert store.get("coach_calendar") == sessions
    assert store.get("coach_draft") == draft
    identities = [item["id"] for item in store.planned_sessions()]
    with store.connect() as db:
        assert not db.execute("SELECT 1 FROM meta WHERE key='coach_calendar'").fetchone()
        raw = json.loads(db.execute("SELECT value FROM meta WHERE key='coach_draft'").fetchone()[0])
        assert "sessions" not in raw["plan"]
        assert (
            json.loads(
                db.execute(
                    "SELECT value FROM meta WHERE key='legacy_coach_calendar_v1'"
                ).fetchone()[0]
            )
            == sessions
        )
    assert [item["id"] for item in Store(tmp_path).planned_sessions()] == identities
    assert secret.read_bytes() == b"unchanged-encrypted-credentials"


def test_migration_failure_rolls_back_legacy_data(tmp_path):
    sessions = plan(date.today()).model_dump(mode="json")["sessions"]
    legacy_database(tmp_path, sessions, None)
    with sqlite3.connect(tmp_path / "planner.sqlite3") as db:
        db.execute("UPDATE meta SET value='invalid JSON' WHERE key='coach_draft'")
    with pytest.raises(json.JSONDecodeError):
        Store(tmp_path)
    with sqlite3.connect(tmp_path / "planner.sqlite3") as db:
        assert (
            json.loads(
                db.execute("SELECT value FROM meta WHERE key='coach_calendar'").fetchone()[0]
            )
            == sessions
        )
        assert not db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='planned_sessions'"
        ).fetchone()


def test_deleting_session_preserves_other_calendar_identity(tmp_path):
    today = date.today()
    store = Store(tmp_path)
    sessions = plan(today).model_dump(mode="json")["sessions"]
    store.set("coach_calendar", sessions)
    before = month_calendar(store, today.year, today.month)["entries"]
    store.remove_coach_session(session_key(sessions[0]))
    after = month_calendar(store, today.year, today.month)["entries"]
    assert {item["id"] for item in after} < {item["id"] for item in before}
    with store.connect() as db:
        assert (
            db.execute("SELECT COUNT(*) FROM planned_sessions WHERE deleted=1").fetchone()[0] == 1
        )


def test_acceptance_preserves_other_week_ids(tmp_path):
    today = date.today()
    store = Store(tmp_path)
    settings = setup(today)
    store.set("coach_setup", settings)
    later = plan(today + timedelta(days=14)).model_dump(mode="json")["sessions"]
    store.set("coach_calendar", later)
    ids = [item["id"] for item in store.planned_sessions()]
    from garmin_planner.coach import fingerprint

    accepted = {
        "id": "test-plan",
        "start": str(today),
        "setup_hash": fingerprint(settings),
        "plan": plan(today).model_dump(mode="json"),
    }
    store.set("coach_draft", accepted)
    store.accept_plan(accepted)
    assert [item["id"] for item in store.planned_sessions(str(today + timedelta(days=14)))] == ids
    assert store.get("coach_draft") is None
    assert not store.planned_sessions(draft=True)


def test_modular_routes_keep_authentication_and_serve_module_assets(tmp_path):
    with TestClient(
        create_app(Settings(_env_file=None, data_dir=tmp_path, auto_sync=False)),
        base_url="http://127.0.0.1:8000",
    ) as client:
        for path in (
            "/api/dashboard",
            "/api/coach",
            "/api/calendar?year=2026&month=10",
            "/api/library",
            "/api/workout-options",
            "/api/connections",
            "/api/pro/models",
        ):
            assert client.get(path).status_code == 401
        home = client.get("/").text
        assert 'type="module"' in home
        assert client.get("/static/modules/calendar.js").status_code == 200
        assert client.get("/static/modules/core.js").status_code == 200
