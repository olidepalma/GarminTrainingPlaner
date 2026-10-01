"""OAuth del cliente propio usando únicamente endpoints oficiales OpenAI."""

import base64
import hashlib
import secrets
import threading
import time
import uuid
from urllib.parse import urlencode, urlparse

import httpx2 as httpx
import jwt

from garmin_planner.storage import Vault

ISSUER = "https://auth.openai.com"
RESOURCE = "https://api.openai.com/v1"
TOKEN_URL = ISSUER + "/api/accounts/oauth/token"
SCOPE = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"


class ProError(Exception):
    pass


def inference_error(event):
    """Mostrar motivos estructurados sin copiar mensajes o contenido del proveedor."""
    response = event.get("response") or {}
    error = response.get("error") or event.get("error") or event
    code = error.get("code") if isinstance(error, dict) else None
    reason = (response.get("incomplete_details") or {}).get("reason")
    explanations = {
        "subscription_sharing_usage_limit_exceeded": (
            "Has alcanzado el límite de uso de tu plan ChatGPT para aplicaciones. "
            "Revisa los límites en ChatGPT y espera a su renovación."
        ),
        "subscription_sharing_usage_unavailable": (
            "El uso de tu plan ChatGPT no está disponible para esta petición. "
            "Revisa los permisos y la disponibilidad de tu cuenta."
        ),
        "rate_limit_exceeded": "OpenAI ha limitado las peticiones. Inténtalo más tarde.",
        "server_error": "OpenAI tuvo un error interno. Puedes intentarlo de nuevo más tarde.",
        "invalid_prompt": "OpenAI rechazó el contexto enviado. Hay que revisar la petición.",
        "model_not_found": (
            "El modelo seleccionado no está disponible. Actualiza la lista de modelos."
        ),
        "context_length_exceeded": "El contexto supera el límite del modelo seleccionado.",
        "max_output_tokens": "OpenAI interrumpió la respuesta al alcanzar su límite de salida. "
        "El plan parcial no se ha guardado; hay que reducir la extensión de la respuesta.",
        "content_filter": "OpenAI interrumpió la respuesta por un filtro de contenido.",
    }
    detail = code or reason
    message = explanations.get(detail, "OpenAI no completó la petición.")
    # Los mensajes libres pueden contener datos del prompt: nunca se muestran ni se registran.
    import re

    if isinstance(detail, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,79}", detail):
        message += f" Código: {detail}."
    else:
        message += (
            " Sin código de diagnóstico; evento: " + str(event.get("type", "unknown"))[:40] + "."
        )
    return ProError(message)


class ProClient:
    def __init__(self, vault: Vault, port: int, http=None):
        self.vault = vault
        self.http = http or httpx.Client(timeout=30, follow_redirects=False)
        self.redirect = f"http://127.0.0.1:{port}/auth/callback"
        self.lock = threading.RLock()
        self.pending: dict[str, dict] = {}
        if not vault.read("host"):
            vault.write("host", {"id": "urn:uuid:" + str(uuid.uuid4())})

    def start(self, session: str, new_account=False) -> str:
        with self.lock:
            self.pending = {k: v for k, v in self.pending.items() if v["expires"] > time.time()}
            previous = None if new_account else self.vault.read("pro")
            state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
            client_id = previous["client_id"] if previous else "dynamic_agent_client"
            self.pending[session] = {
                "state": state,
                "nonce": nonce,
                "verifier": verifier,
                "client_id": client_id,
                "previous": previous,
                "expires": time.time() + 600,
            }
            params = {
                "client_id": client_id,
                "ext_agent_host_id": self.vault.read("host")["id"],
                "response_type": "code",
                "redirect_uri": self.redirect,
                "scope": SCOPE,
                "resource": RESOURCE,
                "state": state,
                "nonce": nonce,
                "code_challenge_method": "S256",
                "code_challenge": base64.urlsafe_b64encode(
                    hashlib.sha256(verifier.encode()).digest()
                )
                .decode()
                .rstrip("="),
            }
            if previous and previous.get("id_token"):
                params["id_token_hint"] = previous["id_token"]
            if not previous:
                params["agent_name_hint"] = "Garmin Training Planner"
            return ISSUER + "/api/accounts/authorize?" + urlencode(params)

    def _discovery(self):
        data = self._json(self.http.get(ISSUER + "/.well-known/openid-configuration"))
        if data.get("issuer") != ISSUER:
            raise ProError("El proveedor no devolvió un issuer válido.")
        for name in ("jwks_uri", "revocation_endpoint"):
            if name in data:
                parsed = urlparse(data[name])
                if parsed.scheme != "https" or parsed.hostname != "auth.openai.com":
                    raise ProError("El proveedor devolvió un endpoint inesperado.")
        return data

    def _identity(self, token: str, client_id: str, nonce: str | None = None) -> dict:
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256":
                raise ProError("Algoritmo del ID token no permitido.")
            discovery = self._discovery()
            keys = jwt.PyJWKSet.from_dict(self._json(self.http.get(discovery["jwks_uri"])))
            key = next(k for k in keys.keys if k.key_id == header.get("kid"))
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                audience=client_id,
                issuer=ISSUER,
                options={"require": ["exp", "iat", "sub", "aud", "iss"]},
            )
            if nonce is not None and not secrets.compare_digest(
                str(claims.get("nonce", "")), nonce
            ):
                raise ProError("Nonce del ID token incorrecto.")
            return claims
        except (jwt.PyJWTError, KeyError, StopIteration, ValueError) as exc:
            raise ProError("No se pudo validar la identidad de OpenAI.") from exc

    @staticmethod
    def _json(response):
        if response.status_code >= 400:
            if response.status_code in (401, 403):
                raise ProError("OpenAI denegó el acceso. Reautoriza el uso de tu plan.")
            if response.status_code == 429:
                raise ProError("OpenAI ha limitado las peticiones. Inténtalo más tarde.")
            raise ProError(f"OpenAI devolvió HTTP {response.status_code}. Reintenta la conexión.")
        return response.json()

    def complete(self, session: str, params: dict) -> None:
        with self.lock:
            pending = self.pending.get(session)
            if not pending or pending["expires"] < time.time():
                raise ProError("La autorización ha caducado. Iníciala otra vez.")
            if not secrets.compare_digest(params.get("state", ""), pending["state"]):
                raise ProError("La autorización no corresponde a esta sesión.")
            del self.pending[session]
            if params.get("error"):
                raise ProError("No se ha autorizado la conexión con ChatGPT.")
            client_id = params.get("client_id", pending["client_id"])
            if client_id == "dynamic_agent_client" or not params.get("code"):
                raise ProError("OpenAI no ha completado el registro del cliente.")
            previous = pending["previous"]
            if previous and client_id != previous["client_id"]:
                raise ProError("El cliente devuelto no coincide con la cuenta seleccionada.")
            tokens = self._json(
                self.http.post(
                    TOKEN_URL,
                    data={
                        "grant_type": "authorization_code",
                        "client_id": client_id,
                        "code": params["code"],
                        "code_verifier": pending["verifier"],
                        "redirect_uri": self.redirect,
                        "resource": RESOURCE,
                    },
                )
            )
            claims = self._identity(tokens["id_token"], client_id, pending["nonce"])
            if previous and claims["sub"] != previous["subject"]:
                raise ProError("La identidad devuelta no coincide con la cuenta seleccionada.")
            record = {
                "client_id": client_id,
                "subject": claims["sub"],
                "email": claims.get("email", "Cuenta ChatGPT"),
            }
            self._save(record, tokens)

    def _save(self, record: dict, tokens: dict):
        if not tokens.get("access_token") or tokens.get("token_type", "").lower() != "bearer":
            raise ProError("OpenAI no devolvió credenciales Bearer válidas.")
        record.update(
            {k: tokens[k] for k in ("access_token", "refresh_token", "id_token") if k in tokens}
        )
        record["scopes"] = tokens.get("scope", " ".join(record.get("scopes", []))).split()
        record["expires_at"] = time.time() + float(tokens.get("expires_in", 3600))
        record["earliest_refresh_at"] = tokens.get("earliest_refresh_at", 0)
        self.vault.write("pro", record)

    def status(self):
        record = self.vault.read("pro")
        if not record or not record.get("access_token"):
            return {"status": "not_connected", "provider": "chatgpt_pro"}
        return {
            "status": "connected"
            if "chatgpt.tokens.use.direct" in record["scopes"]
            else "permission_required",
            "provider": "chatgpt_pro",
            "email": record["email"],
            "expires_at": record["expires_at"],
        }

    def access_token(self) -> str:
        with self.lock:
            record = self.vault.read("pro")
            if not record or not record.get("access_token"):
                raise ProError("Conecta primero tu cuenta ChatGPT.")
            if "chatgpt.tokens.use.direct" not in record.get("scopes", []):
                raise ProError("Autoriza el uso de tu plan ChatGPT para esta aplicación.")
            if record["expires_at"] <= time.time() + 60:
                if not record.get("refresh_token"):
                    raise ProError("La sesión ha caducado. Conecta otra vez ChatGPT.")
                earliest = record.get("earliest_refresh_at", 0)
                if isinstance(earliest, (int, float)) and earliest > time.time():
                    raise ProError("OpenAI todavía no permite renovar esta sesión.")
                tokens = self._json(
                    self.http.post(
                        TOKEN_URL,
                        data={
                            "grant_type": "refresh_token",
                            "client_id": record["client_id"],
                            "refresh_token": record["refresh_token"],
                            "resource": RESOURCE,
                        },
                    )
                )
                if tokens.get("id_token"):
                    claims = self._identity(tokens["id_token"], record["client_id"])
                    if claims["sub"] != record["subject"]:
                        raise ProError("La renovación devolvió otra identidad.")
                self._save(record, tokens)
            return record["access_token"]

    def models(self):
        data = self._json(
            self.http.get(
                RESOURCE + "/models", headers={"Authorization": "Bearer " + self.access_token()}
            )
        )
        return [
            {"id": m["slug"], "name": m.get("display_name", m["slug"])}
            for m in data.get("models", [])
            if m.get("visibility") == "list"
        ]

    def test(self, model: str):
        return self.respond(model, "Responde solo: Conexión correcta.")

    def respond(self, model: str, prompt: str, instructions: str | None = None):
        if model not in {m["id"] for m in self.models()}:
            raise ProError("Selecciona un modelo disponible para tu cuenta.")
        text, completed, usage = "", False, None
        with self.http.stream(
            "POST",
            RESOURCE + "/responses",
            timeout=180,
            headers={"Authorization": "Bearer " + self.access_token()},
            json={
                "model": model,
                "input": ([{"role": "developer", "content": instructions}] if instructions else [])
                + [{"role": "user", "content": prompt}],
                "store": False,
                "stream": True,
            },
        ) as response:
            if response.status_code >= 400:
                self._json(response)
            import json

            buffer = []

            def lines_with_end():
                yield from response.iter_lines()
                yield ""

            for line in lines_with_end():
                if line.startswith("data:"):
                    buffer.append(line[5:].strip())
                elif not line and buffer:
                    raw, buffer = "\n".join(buffer), []
                    if raw == "[DONE]":
                        continue
                    event = json.loads(raw)
                    if event.get("type") == "response.output_text.delta":
                        text += event.get("delta", "")
                    if event.get("type") in ("response.failed", "response.incomplete", "error"):
                        raise inference_error(event)
                    if event.get("type") == "response.completed":
                        completed = True
                        usage = event.get("response", {}).get("usage")
                        if not text:
                            text = "".join(
                                part.get("text", "")
                                for item in event.get("response", {}).get("output", [])
                                for part in item.get("content", [])
                                if part.get("type") == "output_text"
                            )
            if not completed:
                raise ProError("La conexión terminó sin confirmar la respuesta.")
        return {"text": text, "usage": usage}

    def disconnect(self):
        with self.lock:
            self.pending.clear()
            record = self.vault.read("pro")
            confirmed = False
            if record and record.get("refresh_token"):
                try:
                    endpoint = self._discovery()["revocation_endpoint"]
                    response = self.http.post(
                        endpoint,
                        data={
                            "token": record["refresh_token"],
                            "token_type_hint": "refresh_token",
                            "client_id": record["client_id"],
                        },
                    )
                    confirmed = response.status_code == 200
                except (httpx.HTTPError, ProError, KeyError):
                    pass
            if record:
                record = {k: record[k] for k in ("client_id", "subject", "email")}
                self.vault.write("pro", record)
            return {"revocation_confirmed": confirmed}
