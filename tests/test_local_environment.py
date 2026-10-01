"""Verifica límites del entorno local y el contrato que ve la usuaria."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from garmin_planner.app import create_app
from garmin_planner.config import Settings


def test_health_reports_without_secrets(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path, auto_sync=False)
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8000") as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["timezone"] == "Europe/Madrid"
        assert "integrations" not in data
        assert "token" not in response.text


def test_packaged_homepage_is_available(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path, auto_sync=False)
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8000") as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Garmin Training Planner" in response.text


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.5"])
def test_local_launcher_rejects_network_exposure(host):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, host=host)


@pytest.mark.parametrize("port", [0, 65536])
def test_invalid_port_is_rejected(port):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, port=port)


def test_iana_timezone_available_on_all_platforms():
    assert Settings(_env_file=None, timezone="Europe/Madrid").timezone == "Europe/Madrid"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, timezone="Invalid/Timezone")


def test_no_paid_api_fallback_can_be_enabled():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, coach_provider="openai_api")


def test_env_file_is_utf8_and_does_not_require_secrets(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# Configuración portátil\nGTP_PORT=8123\n", encoding="utf-8")
    assert Settings(_env_file=env).port == 8123


def test_https_proxy_private_session_and_origin(tmp_path):
    from garmin_planner.storage import Store

    Store(tmp_path).setup("test-private-password")
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        auto_sync=False,
        public_origin="https://training.example.com",
    )
    with TestClient(create_app(settings), base_url="https://training.example.com") as client:
        response = client.get("/api/session")
        assert "Secure" in response.headers["set-cookie"]
        csrf = response.json()["csrf"]
        headers = {"Origin": "https://training.example.com", "X-CSRF-Token": csrf}
        assert (
            client.post(
                "/api/session/login", json={"password": "test-private-password"}, headers=headers
            ).status_code
            == 200
        )
        assert client.get("/api/dashboard").status_code == 200
        assert (
            client.post(
                "/api/session/logout",
                json={},
                headers={"Origin": "https://evil.example", "X-CSRF-Token": csrf},
            ).status_code
            == 403
        )
        assert client.get("/api/health", headers={"Host": "evil.example"}).status_code == 400
    with TestClient(create_app(settings), base_url="http://training.example.com") as client:
        assert client.get("/api/session").status_code == 400


def test_initial_password_cannot_be_claimed_through_public_domain(tmp_path):
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        auto_sync=False,
        public_origin="https://training.example.com",
    )
    with TestClient(create_app(settings), base_url="https://training.example.com") as client:
        csrf = client.get("/api/session").json()["csrf"]
        assert (
            client.post(
                "/api/session/login",
                json={"password": "test-private-password"},
                headers={"Origin": "https://training.example.com", "X-CSRF-Token": csrf},
            ).status_code
            == 403
        )
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8000") as client:
        csrf = client.get("/api/session").json()["csrf"]
        assert (
            client.post(
                "/api/session/login",
                json={"password": "test-private-password"},
                headers={"Origin": "http://127.0.0.1:8000", "X-CSRF-Token": csrf},
            ).status_code
            == 200
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://training.example.com",
        "https://user:pass@training.example.com",
        "https://training.example.com/secret",
        "https://training.example.com?token=x",
    ],
)
def test_public_origin_is_exact_https_origin(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, public_origin=url)


def test_network_listener_requires_https_and_specific_proxy():
    assert (
        Settings(
            _env_file=None, host="192.168.1.50", public_origin="https://training.example.com"
        ).host
        == "192.168.1.50"
    )
    assert (
        Settings(_env_file=None, host="0.0.0.0", public_origin="https://training.example.com").host
        == "0.0.0.0"
    )
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None, public_origin="https://training.example.com", trusted_proxy_ips="*"
        )
