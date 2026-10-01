import json
from datetime import UTC, datetime, timedelta

import pytest

from garmin_planner.config import Settings
from garmin_planner.garmin import GarminError, GarminService, dashboard, normalize
from garmin_planner.storage import Store, Vault


class ClientTokens:
    def dumps(self):
        return json.dumps({"di_token": "garmin-access", "di_refresh_token": "garmin-refresh"})


class GarminFake:
    display_name = "same-account"
    full_name = "Athlete"
    requested = []
    duration = 1800
    fail = False

    def __init__(self, *args, **kwargs):
        self.client = ClientTokens()
        self.prompt = kwargs.get("prompt_mfa")
        self.password = None

    def login(self, tokens=None):
        if self.prompt:
            assert self.prompt() == "123456"

    def get_activities_by_date(self, start, end):
        self.requested.append((start, end))
        if self.fail:
            raise RuntimeError("sensitive upstream error")
        today = datetime.now(UTC).date()
        return [
            {
                "activityId": 123,
                "activityName": "Run",
                "startTimeLocal": today.isoformat() + " 09:00:00",
                "activityType": {"typeKey": "running"},
                "duration": self.duration,
                "distance": 5000,
                "elevationGain": 80,
            }
        ]

    def get_stats(self, day):
        return {"totalSteps": 9000, "restingHeartRate": 52}


@pytest.fixture
def service(tmp_path):
    GarminFake.requested = []
    GarminFake.duration = 1800
    GarminFake.fail = False
    return GarminService(
        Settings(_env_file=None, data_dir=tmp_path, timezone="UTC"),
        Store(tmp_path),
        Vault(tmp_path),
        factory=GarminFake,
    )


def test_mfa_connection_and_incremental_updates_without_duplicates(service):
    service.connect("athlete@example.test", "password", lambda: "123456")
    service.sync()
    first = GarminFake.requested[-1]
    GarminFake.duration = 2400
    service.sync()
    second = GarminFake.requested[-1]
    assert first[0] < second[0]
    data = dashboard(service.store, "UTC", 90)
    assert data["totals"]["sessions"] == 1
    assert data["activities"][0]["duration_seconds"] == 2400
    assert len(data["wellness"]) == 7
    assert b"garmin-refresh" not in (service.vault.root / "garmin.enc").read_bytes()


def test_failed_sync_preserves_existing_data_and_cursor(service):
    service.connect("athlete@example.test", "password", lambda: "123456")
    service.sync()
    previous = service.store.get("sync")
    GarminFake.fail = True
    with pytest.raises(RuntimeError):
        service.sync()
    assert service.store.get("sync") == previous
    assert dashboard(service.store, "UTC")["totals"]["sessions"] == 1


def test_garmin_account_switch_cannot_mix_histories(service):
    service.store.set("garmin_identity", "different-account")
    with pytest.raises(GarminError):
        service.connect("athlete@example.test", "password", lambda: "123456")
    assert service.vault.read("garmin") is None


def test_utc_conversion_and_trail_classification():
    raw = {
        "activityId": 1,
        "startTimeGMT": "2026-09-30 23:30:00",
        "activityType": {"typeKey": "trail_running"},
        "duration": float("nan"),
        "distance": -1,
    }
    row = normalize(raw, "Europe/Madrid")
    assert row["day"] == "2026-10-01" and row["sport"] == "trail"
    assert row["duration_seconds"] == 0 and row["distance_m"] == 0


def test_sport_filter_and_empty_weeks_are_correct(service):
    today = datetime.now(UTC).date()
    rows = [
        {
            "id": "1",
            "day": today.isoformat(),
            "sport": "running",
            "duration_seconds": 3600,
            "distance_m": 10000,
            "elevation_m": 120,
        },
        {
            "id": "2",
            "day": (today - timedelta(days=7)).isoformat(),
            "sport": "cycling",
            "duration_seconds": 7200,
            "distance_m": 40000,
            "elevation_m": 400,
        },
    ]
    service.store.save_activities(rows, {})
    data = dashboard(service.store, "UTC", 28, "running")
    assert data["totals"]["sessions"] == 1
    assert data["totals"]["distance_km"] == 10
    assert sum(w["hours"] for w in data["weeks"]) == 1
    assert any(w["sessions"] == 0 for w in data["weeks"])
