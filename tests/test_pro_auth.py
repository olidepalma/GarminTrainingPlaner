import json
import time
from contextlib import contextmanager
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from garmin_planner.pro import ISSUER, RESOURCE, TOKEN_URL, ProClient, ProError
from garmin_planner.storage import Vault


class Response:
    status_code = 200

    def __init__(self, data=None, lines=None):
        self.data, self.lines = data, lines

    def json(self):
        return self.data

    def iter_lines(self):
        return iter(self.lines)


class HTTP:
    def __init__(self, key):
        self.key = key
        self.calls = []
        self.tokens = None
        self.events = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        if url.endswith("openid-configuration"):
            return Response(
                {
                    "issuer": ISSUER,
                    "jwks_uri": ISSUER + "/jwks",
                    "revocation_endpoint": ISSUER + "/revoke",
                }
            )
        if url.endswith("/jwks"):
            key = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
            key["kid"] = "test-key"
            return Response({"keys": [key]})
        if url.endswith("/models"):
            return Response(
                {
                    "models": [
                        {
                            "slug": "eligible-model",
                            "display_name": "Eligible",
                            "visibility": "list",
                        },
                        {"slug": "hidden", "visibility": "hidden"},
                    ]
                }
            )
        raise AssertionError(url)

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return Response(self.tokens)

    @contextmanager
    def stream(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        yield Response(
            lines=[line for event in self.events for line in ("data: " + json.dumps(event), "")]
        )


@pytest.fixture
def fixture(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    http = HTTP(key)
    client = ProClient(Vault(tmp_path), 8000, http=http)
    return client, http, key


def authorize(fixture, **overrides):
    client, http, key = fixture
    query = parse_qs(urlparse(client.start("session")).query)
    claims = {
        "iss": ISSUER,
        "aud": "own-client",
        "sub": "subject",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        "nonce": query["nonce"][0],
        "email": "athlete@example.test",
    }
    claims.update(overrides)
    http.tokens = {
        "id_token": jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-key"}),
        "access_token": "access-secret",
        "refresh_token": "refresh-secret",
        "scope": "openid chatgpt.tokens.use.direct",
        "token_type": "Bearer",
        "expires_in": 3600,
    }
    client.complete(
        "session", {"state": query["state"][0], "code": "code", "client_id": "own-client"}
    )
    return query


def test_pkce_dynamic_registration_and_encrypted_credentials(fixture):
    client, http, _ = fixture
    query = authorize(fixture)
    assert query["client_id"] == ["dynamic_agent_client"]
    assert query["redirect_uri"] == ["http://127.0.0.1:8000/auth/callback"]
    assert query["resource"] == [RESOURCE]
    assert query["code_challenge_method"] == ["S256"]
    assert query["ext_agent_host_id"][0].startswith("urn:uuid:")
    request = next(call for call in http.calls if call[0] == "POST")
    assert request[1] == TOKEN_URL
    assert request[2]["data"]["client_id"] == "own-client"
    assert request[2]["data"]["redirect_uri"] == query["redirect_uri"][0]
    assert client.status()["status"] == "connected"
    assert b"access-secret" not in (client.vault.root / "pro.enc").read_bytes()
    returning = parse_qs(urlparse(client.start("session")).query)
    assert returning["client_id"] == ["own-client"]
    assert "agent_name_hint" not in returning


@pytest.mark.parametrize(
    "overrides",
    [{"nonce": "wrong"}, {"aud": "other-client"}, {"iss": "https://evil.example"}, {"exp": 1}],
)
def test_invalid_identity_is_not_saved(fixture, overrides):
    client, _, _ = fixture
    with pytest.raises(ProError):
        authorize(fixture, **overrides)
    assert client.vault.read("pro") is None


def test_state_checked_before_token_exchange(fixture):
    client, http, _ = fixture
    client.start("session")
    with pytest.raises(ProError):
        client.complete("session", {"state": "wrong", "code": "code", "client_id": "own-client"})
    assert not http.calls


def test_missing_dynamic_client_rejected(fixture):
    client, http, _ = fixture
    q = parse_qs(urlparse(client.start("session")).query)
    with pytest.raises(ProError):
        client.complete("session", {"state": q["state"][0], "code": "code"})
    assert not http.calls


def test_refresh_rotates_token_with_own_client_and_preserves_scope(fixture):
    client, http, _ = fixture
    authorize(fixture)
    record = client.vault.read("pro")
    record["expires_at"] = 0
    client.vault.write("pro", record)
    http.tokens = {
        "access_token": "new-access",
        "refresh_token": "new-refresh",
        "token_type": "Bearer",
        "expires_in": 3600,
    }
    assert client.access_token() == "new-access"
    assert client.vault.read("pro")["refresh_token"] == "new-refresh"
    assert http.calls[-1][2]["data"]["client_id"] == "own-client"
    assert "scope" not in http.calls[-1][2]["data"]


def test_inference_preview_contract_and_completion(fixture):
    client, http, _ = fixture
    authorize(fixture)
    http.events = [
        {"type": "response.output_text.delta", "delta": "Conexión correcta."},
        {"type": "response.completed", "response": {"usage": {"total_tokens": 12}}},
    ]
    result = client.test("eligible-model")
    assert result["usage"]["total_tokens"] == 12
    request = http.calls[-1][2]["json"]
    assert request["store"] is False and request["stream"] is True
    assert "max_output_tokens" not in request
    assert "previous_response_id" not in request
    assert len(request["input"]) == 1
    http.events = [{"type": "response.output_text.delta", "delta": "Partial"}]
    with pytest.raises(ProError):
        client.test("eligible-model")


def test_coach_rules_are_separate_from_untrusted_context(fixture):
    client, http, _ = fixture
    authorize(fixture)
    http.events = [
        {"type": "response.output_text.delta", "delta": "{}"},
        {"type": "response.completed", "response": {"usage": {}}},
    ]
    client.respond(
        "eligible-model",
        '{"sources": [{"text":"Untrusted book extract"}]}',
        instructions="Follow the coaching rules.",
    )
    messages = http.calls[-1][2]["json"]["input"]
    assert messages[0] == {"role": "developer", "content": "Follow the coaching rules."}
    assert messages[1]["role"] == "user"
    assert "Untrusted book extract" in messages[1]["content"]


@pytest.mark.parametrize(
    "event, expected",
    [
        (
            {
                "type": "response.failed",
                "response": {
                    "error": {
                        "code": "subscription_sharing_usage_limit_exceeded",
                        "message": "PRIVATE PROMPT",
                    }
                },
            },
            "límite de uso",
        ),
        (
            {
                "type": "response.failed",
                "response": {"error": {"code": "server_error", "message": "PRIVATE PROMPT"}},
            },
            "error interno",
        ),
        (
            {
                "type": "response.incomplete",
                "response": {"incomplete_details": {"reason": "max_output_tokens"}},
            },
            "límite de salida",
        ),
        (
            {"type": "error", "code": "context_length_exceeded", "message": "PRIVATE PROMPT"},
            "contexto supera",
        ),
    ],
)
def test_stream_failures_show_safe_actionable_reason(fixture, event, expected):
    client, http, _ = fixture
    authorize(fixture)
    http.events = [event]
    with pytest.raises(ProError, match=expected) as exc:
        client.respond("eligible-model", "PRIVATE PROMPT")
    assert "PRIVATE PROMPT" not in str(exc.value)
    assert "Código:" in str(exc.value)


def test_terminal_event_without_trailing_sse_separator(fixture, monkeypatch):
    client, http, _ = fixture
    authorize(fixture)
    http.events = [
        {"type": "response.output_text.delta", "delta": "Complete"},
        {"type": "response.completed", "response": {"usage": {"total_tokens": 5}}},
    ]
    monkeypatch.setattr(Response, "iter_lines", lambda self: iter(self.lines[:-1]))
    assert client.respond("eligible-model", "Test")["text"] == "Complete"


def test_completed_output_without_deltas_is_collected(fixture):
    client, http, _ = fixture
    authorize(fixture)
    http.events = [
        {
            "type": "response.completed",
            "response": {
                "output": [
                    {"type": "message", "content": [{"type": "output_text", "text": "Final text"}]}
                ],
                "usage": {},
            },
        }
    ]
    assert client.respond("eligible-model", "Test")["text"] == "Final text"
