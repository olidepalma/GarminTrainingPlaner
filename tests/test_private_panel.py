import pytest
from fastapi.testclient import TestClient

from garmin_planner.app import create_app
from garmin_planner.config import Settings

BASE = "http://127.0.0.1:8000"


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(_env_file=None, data_dir=tmp_path, auto_sync=False))
    with TestClient(app, base_url=BASE) as client:
        yield client


def headers(client):
    return {"Origin": BASE, "X-CSRF-Token": client.get("/api/session").json()["csrf"]}


def login(client):
    response = client.post(
        "/api/session/login", json={"password": "my-private-password"}, headers=headers(client)
    )
    assert response.status_code == 200
    return {"Origin": BASE, "X-CSRF-Token": response.json()["csrf"]}


@pytest.mark.parametrize(
    "path",
    [
        "/api/dashboard",
        "/api/connections",
        "/api/pro/models",
        "/api/jobs/anything",
        "/api/calendar?year=2026&month=10",
        "/api/sports-statistics",
        "/api/race-distances",
    ],
)
def test_personal_data_requires_auth(client, path):
    assert client.get(path).status_code == 401


def test_setup_login_logout_and_session_rotation(client):
    initial = client.get("/api/session").json()
    old_cookie = client.cookies.get("gtp_session")
    h = login(client)
    assert initial["setup_required"]
    assert client.cookies.get("gtp_session") != old_cookie
    assert client.get("/api/dashboard").status_code == 200
    assert client.get("/api/dashboard").json()["totals"]["sessions"] == 0
    assert client.post("/api/session/logout", json={}, headers=h).status_code == 200
    assert client.get("/api/dashboard").status_code == 401
    assert not client.get("/api/session").json()["setup_required"]
    assert (
        client.post(
            "/api/session/login", json={"password": "wrong-password"}, headers=headers(client)
        ).status_code
        == 401
    )
    login(client)


def test_origin_csrf_and_host_are_checked(client):
    h = login(client)
    assert (
        client.post("/api/wellness-options", json={}, headers={"Origin": BASE}).status_code == 403
    )
    assert (
        client.post(
            "/api/wellness-options", json={}, headers={**h, "Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert client.get("/api/health", headers={"Host": "evil.example"}).status_code == 400
    assert client.post("/api/wellness-options", json={"sleep": True}, headers=h).status_code == 200
    assert client.get("/api/dashboard").json()["wellness_options"]["sleep"]


def test_password_not_in_validation_errors(client):
    h = login(client)
    password = "private-garmin-password"
    response = client.post(
        "/api/garmin/connect", json={"email": "x", "password": password}, headers=h
    )
    assert response.status_code == 422
    assert password not in response.text


def test_login_is_rate_limited(client):
    login(client)
    client.post("/api/session/logout", json={}, headers=headers(client))
    h = headers(client)
    for _ in range(4):
        assert (
            client.post(
                "/api/session/login", json={"password": "wrong-password"}, headers=h
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/session/login", json={"password": "wrong-password"}, headers=h
        ).status_code
        == 429
    )


def test_connections_no_network_or_tokens(client):
    login(client)
    data = client.get("/api/connections").json()
    assert data["garmin"]["status"] == "not_connected"
    assert data["pro"]["status"] == "not_connected"
    assert "token" not in str(data)
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200
    assert client.get("/docs").status_code == 404
    assert client.get("/data/planner.sqlite3").status_code == 404
