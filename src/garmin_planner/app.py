"""Panel privado local con sesión y protección CSRF."""

import asyncio
import secrets
import sqlite3
import threading
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from importlib.resources import files
from typing import Literal
from zoneinfo import ZoneInfo

import httpx2 as httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from filelock import FileLock, Timeout
from pydantic import BaseModel, Field, SecretStr
from starlette.middleware.trustedhost import TrustedHostMiddleware

from garmin_planner import __version__
from garmin_planner.calendar import month_calendar
from garmin_planner.coach import Accept, Coach, Generate, Setup
from garmin_planner.config import Settings
from garmin_planner.garmin import GarminError, GarminService, dashboard
from garmin_planner.jobs import BusyError, Jobs
from garmin_planner.library import MAX_UPLOAD, Library
from garmin_planner.pro import ProClient, ProError
from garmin_planner.review import Feedback, weekly_review
from garmin_planner.sports_data import DISTANCES
from garmin_planner.storage import Store, Vault, private_dir
from garmin_planner.workouts import Workout, Workouts

COOKIE = "gtp_session"


class PasswordBody(BaseModel):
    password: SecretStr


class GarminBody(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: SecretStr


class MFABody(BaseModel):
    code: str = Field(min_length=4, max_length=12, pattern=r"^[0-9]+$")


class ModelBody(BaseModel):
    model: str = Field(min_length=1, max_length=100)


class OptionsBody(BaseModel):
    sleep: bool = False
    hrv: bool = False


class CoachWorkoutBody(BaseModel):
    source: str = Field(pattern=r"^[0-9a-f]{64}$")


class SendWorkoutBody(BaseModel):
    revision: str = Field(pattern=r"^[0-9a-f]{64}$")


class EnabledBody(BaseModel):
    enabled: bool


class ProStartBody(BaseModel):
    new_account: bool = False


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else Settings()
    root = config.data_dir.absolute()

    @asynccontextmanager
    async def lifespan(app):
        private_dir(root)
        lock = FileLock(root / "runtime.lock")
        try:
            lock.acquire(timeout=0)
        except Timeout as exc:
            raise RuntimeError("Ya hay un servidor usando esta carpeta GTP_DATA_DIR.") from exc
        app.state.store = Store(root)
        app.state.library = Library(app.state.store)
        app.state.vault = Vault(root)
        app.state.jobs = Jobs()
        app.state.pro = ProClient(app.state.vault, config.port)
        app.state.garmin = GarminService(config, app.state.store, app.state.vault)
        app.state.workouts = Workouts(app.state.store, app.state.garmin)

        async def scheduler():
            while True:
                now = datetime.now(ZoneInfo(config.timezone))
                day = now.date().isoformat()
                if (
                    config.auto_sync
                    and now.hour >= config.sync_hour
                    and app.state.vault.read("garmin")
                    and app.state.store.get("nightly_attempt") != day
                ):
                    try:
                        start_sync()
                        app.state.store.set("nightly_attempt", day)
                    except BusyError:
                        pass
                await asyncio.sleep(30)

        task = asyncio.create_task(scheduler())
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            await asyncio.to_thread(app.state.jobs.close)
            app.state.pro.http.close()
            lock.release()

    app = FastAPI(
        title="Garmin Training Planner",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    allowed_hosts = ["127.0.0.1", "localhost", "[::1]"]
    if config.public_origin:
        from urllib.parse import urlsplit

        allowed_hosts.append(urlsplit(config.public_origin).hostname)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    @app.middleware("http")
    async def private_responses(request, call_next):
        if (
            config.public_origin
            and request.url.hostname == urlsplit(config.public_origin).hostname
            and request.url.scheme != "https"
        ):
            return JSONResponse(
                {"detail": "El acceso por dominio requiere HTTPS."}, status_code=400
            )
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        detail = "Revisa los campos enviados."
        if request.url.path.startswith("/api/coach/") or request.url.path.startswith(
            "/api/workouts"
        ):
            detail = "; ".join(
                str(error["msg"]).removeprefix("Value error, ") for error in exc.errors()[:3]
            )
        return JSONResponse({"detail": detail}, status_code=422)

    async def integration_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    for error in (ProError, GarminError, BusyError):
        app.add_exception_handler(error, integration_error)

    @app.exception_handler(httpx.HTTPError)
    async def network_error(request, exc):
        return JSONResponse(
            {"detail": "No se pudo contactar con OpenAI. Inténtalo más tarde."}, status_code=502
        )

    def session(request: Request):
        record = app.state.store.session(request.cookies.get(COOKIE))
        if not record:
            raise HTTPException(401, "Inicia sesión en el panel.")
        if request.method not in ("GET", "HEAD"):
            origins = {
                f"http://127.0.0.1:{config.port}",
                f"http://localhost:{config.port}",
                f"http://[::1]:{config.port}",
            }
            if config.public_origin:
                origins.add(config.public_origin)
            if request.headers.get("origin") not in origins or not secrets.compare_digest(
                request.headers.get("x-csrf-token", ""), record["csrf"]
            ):
                raise HTTPException(403, "La solicitud no procede de tu sesión del panel.")
        return record

    def authenticated(record=Depends(session)):
        if not record["authenticated"]:
            raise HTTPException(401, "Inicia sesión en el panel.")
        return record

    def set_cookie(response, sid, request):
        response.set_cookie(
            COOKIE,
            sid,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="lax",
            max_age=43200,
            path="/",
        )

    assets = files("garmin_planner").joinpath("static")
    app.mount("/static", StaticFiles(directory=str(assets)), name="static")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def home():
        return assets.joinpath("index.html").read_text(encoding="utf-8")

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "version": __version__,
            "timezone": config.timezone,
            "mode": "https_proxy" if config.public_origin else "local_development",
        }

    @app.get("/api/session")
    def get_session(request: Request):
        record = app.state.store.session(request.cookies.get(COOKIE))
        sid = None
        if not record:
            sid, record = app.state.store.new_session()
        response = JSONResponse(
            {
                "authenticated": bool(record["authenticated"]),
                "setup_required": not bool(app.state.store.get("password")),
                "csrf": record["csrf"],
            }
        )
        if sid:
            set_cookie(response, sid, request)
        return response

    login_attempts = []
    login_lock = threading.Lock()

    @app.post("/api/session/login")
    def login(body: PasswordBody, request: Request, record=Depends(session)):
        with login_lock:
            login_attempts[:] = [t for t in login_attempts if t > time.time() - 300]
            if len(login_attempts) >= 5:
                raise HTTPException(429, "Demasiados intentos. Espera cinco minutos.")
            password = body.password.get_secret_value()
            if len(password) > 1024:
                raise HTTPException(422, "Contraseña demasiado larga.")
            login_attempts.append(time.time())
            if not app.state.store.get("password"):
                if config.public_origin and request.url.hostname not in (
                    "127.0.0.1",
                    "localhost",
                    "::1",
                ):
                    raise HTTPException(403, "Crea primero la contraseña desde el túnel SSH local.")
                if len(password) < 12:
                    raise HTTPException(422, "Elige una contraseña de al menos doce caracteres.")
                try:
                    app.state.store.setup(password)
                except sqlite3.IntegrityError as exc:
                    raise HTTPException(
                        409, "La contraseña ya se ha configurado. Inicia sesión."
                    ) from exc
            elif not app.state.store.check_password(password):
                raise HTTPException(401, "Contraseña incorrecta.")
        app.state.store.end_session(request.cookies[COOKIE])
        sid, record = app.state.store.new_session(authenticated=True)
        response = JSONResponse({"authenticated": True, "csrf": record["csrf"]})
        set_cookie(response, sid, request)
        return response

    @app.post("/api/session/logout")
    def logout(request: Request, record=Depends(authenticated)):
        app.state.store.end_session(request.cookies[COOKIE])
        response = JSONResponse({"ok": True})
        response.delete_cookie(COOKIE)
        return response

    @app.get("/api/connections", dependencies=[Depends(authenticated)])
    def connections():
        return {
            "garmin": app.state.garmin.status(),
            "pro": app.state.pro.status(),
            "nightly": {
                "hour": config.sync_hour,
                "timezone": config.timezone,
                "enabled": config.auto_sync,
            },
        }

    @app.get("/api/dashboard", dependencies=[Depends(authenticated)])
    def get_dashboard(
        days: int = Query(default=28, ge=7, le=365),
        sport: Literal["running", "trail", "cycling", "swimming", "strength", "triathlon", "other"]
        | None = None,
    ):
        return dashboard(app.state.store, config.timezone, days, sport)

    @app.post("/api/wellness-options", dependencies=[Depends(authenticated)])
    def wellness_options(body: OptionsBody):
        app.state.store.set("wellness_options", body.model_dump())
        return {"ok": True}

    @app.post("/api/garmin/connect", dependencies=[Depends(authenticated)])
    def garmin_connect(body: GarminBody):
        password = body.password.get_secret_value()
        if not 1 <= len(password) <= 1024:
            raise HTTPException(422, "Introduce tu contraseña Garmin.")
        identifier = app.state.jobs.start(
            "garmin",
            lambda job: app.state.garmin.connect(
                body.email, password, lambda: app.state.jobs.prompt_mfa(job)
            ),
        )
        return {"job_id": identifier}

    @app.post("/api/jobs/{identifier}/mfa", dependencies=[Depends(authenticated)])
    def submit_mfa(identifier: str, body: MFABody):
        app.state.jobs.submit_mfa(identifier, body.code)
        return {"ok": True}

    @app.get("/api/jobs/{identifier}", dependencies=[Depends(authenticated)])
    def job_status(identifier: str):
        item = app.state.jobs.get(identifier)
        if not item:
            raise HTTPException(404, "Trabajo no encontrado; puede haberse reiniciado el servidor.")
        return item

    def start_sync():
        def work(job):
            try:
                return app.state.garmin.sync(lambda msg: app.state.jobs.update(job, message=msg))
            except Exception:
                app.state.store.set(
                    "sync_attempt", {"at": datetime.now(UTC).isoformat(), "status": "failed"}
                )
                raise

        return app.state.jobs.start("garmin", work)

    @app.post("/api/garmin/sync", dependencies=[Depends(authenticated)])
    def sync():
        if not app.state.vault.read("garmin"):
            raise GarminError("Conecta primero Garmin.")
        return {"job_id": start_sync()}

    @app.post("/api/garmin/disconnect", dependencies=[Depends(authenticated)])
    def disconnect_garmin():
        def disconnect(job):
            app.state.vault.delete("garmin")
            return {"ok": True}

        return {"job_id": app.state.jobs.start("garmin", disconnect)}

    @app.post("/api/pro/start", dependencies=[Depends(authenticated)])
    def pro_start(body: ProStartBody, request: Request):
        return {"url": app.state.pro.start(request.cookies[COOKIE], body.new_account)}

    @app.get("/auth/callback")
    def pro_callback(request: Request, record=Depends(authenticated)):
        try:
            app.state.pro.complete(request.cookies[COOKIE], dict(request.query_params))
            notice = "Cuenta ChatGPT conectada. Comprueba los permisos en Conexiones."
        except (ProError, httpx.HTTPError, KeyError, ValueError):
            notice = "OpenAI no completó la autorización. Reintenta desde Conexiones."
        app.state.store.set("pro_notice", notice)
        return RedirectResponse("/#connections", status_code=303)

    @app.get("/api/pro/notice", dependencies=[Depends(authenticated)])
    def pro_notice():
        return {"message": app.state.store.get("pro_notice")}

    @app.get("/api/pro/models", dependencies=[Depends(authenticated)])
    def pro_models():
        return {"models": app.state.pro.models()}

    @app.post("/api/pro/test", dependencies=[Depends(authenticated)])
    def pro_test(body: ModelBody):
        def work(job):
            result = app.state.pro.test(body.model)
            app.state.store.set(
                "pro_test",
                {
                    "at": datetime.now(UTC).isoformat(),
                    "model": body.model,
                    "usage": result["usage"],
                },
            )
            return result

        return {"job_id": app.state.jobs.start("pro", work)}

    @app.post("/api/pro/disconnect", dependencies=[Depends(authenticated)])
    def disconnect_pro():
        return {"job_id": app.state.jobs.start("pro", lambda job: app.state.pro.disconnect())}

    @app.get("/api/calendar", dependencies=[Depends(authenticated)])
    def calendar_month(year: int = Query(ge=2000, le=2100), month: int = Query(ge=1, le=12)):
        return month_calendar(app.state.store, year, month, app.state.workouts)

    @app.get("/api/sports-statistics", dependencies=[Depends(authenticated)])
    def sports_statistics():
        return app.state.store.get("garmin_references", {"groups": {}})

    @app.get("/api/race-distances", dependencies=[Depends(authenticated)])
    def race_distances():
        return {"catalog": DISTANCES}

    @app.get("/api/coach", dependencies=[Depends(authenticated)])
    def coach_state():
        return {
            key: app.state.store.get("coach_" + key)
            for key in ("setup", "draft", "accepted", "calendar")
        }

    @app.post("/api/coach/setup", dependencies=[Depends(authenticated)])
    def coach_setup(body: Setup):
        app.state.store.set("coach_setup", body.model_dump(mode="json"))
        return {"ok": True}

    @app.post("/api/coach/generate", dependencies=[Depends(authenticated)])
    def coach_generate(body: Generate):
        coach = Coach(app.state.store, app.state.pro, config.timezone, app.state.library)
        return {"job_id": app.state.jobs.start("pro", lambda job: coach.generate(body))}

    @app.post("/api/coach/accept", dependencies=[Depends(authenticated)])
    def coach_accept(body: Accept):
        return Coach(app.state.store, app.state.pro, config.timezone).accept(body)

    @app.get("/api/library", dependencies=[Depends(authenticated)])
    def library_state():
        return app.state.library.listing()

    @app.post("/api/library/upload", dependencies=[Depends(authenticated)])
    async def library_upload(
        request: Request,
        filename: str = Query(min_length=1, max_length=250),
        title: str = Query(default="", max_length=200),
        author: str = Query(default="", max_length=200),
        document_id: str | None = Query(default=None, pattern=r"^[0-9a-f]{32}$"),
    ):
        content = bytearray()
        async for chunk in request.stream():
            if len(content) + len(chunk) > MAX_UPLOAD:
                raise HTTPException(413, "El archivo supera el límite de 40 MB.")
            content.extend(chunk)
        return await asyncio.to_thread(
            app.state.library.upload, content, filename, title, author, document_id
        )

    @app.post("/api/library/{identifier}/process", dependencies=[Depends(authenticated)])
    def library_process(identifier: str):
        return {
            "job_id": app.state.jobs.start(
                "library", lambda job: app.state.library.process(identifier)
            )
        }

    @app.post("/api/library/{identifier}/enabled", dependencies=[Depends(authenticated)])
    def library_enabled(identifier: str, body: EnabledBody):
        return app.state.library.enable(identifier, body.enabled)

    @app.get("/api/library/{identifier}/preview", dependencies=[Depends(authenticated)])
    def library_preview(identifier: str):
        return app.state.library.preview(identifier)

    @app.get("/api/coach/review", dependencies=[Depends(authenticated)])
    def coach_review():
        return weekly_review(app.state.store, datetime.now(ZoneInfo(config.timezone)).date())

    @app.post("/api/coach/feedback", dependencies=[Depends(authenticated)])
    def coach_feedback(body: Feedback):
        today = datetime.now(ZoneInfo(config.timezone)).date()
        if body.week_start != today - timedelta(days=7):
            raise HTTPException(409, "La semana de revisión cambió. Actualiza la página.")
        data = app.state.store.get("coach_feedback", {})
        data[body.week_start.isoformat()] = body.model_dump(mode="json")
        app.state.store.set("coach_feedback", dict(sorted(data.items())[-52:]))
        return {"ok": True}

    @app.post("/api/workouts", dependencies=[Depends(authenticated)])
    def create_workout(body: Workout):
        return app.state.workouts.save(body)

    @app.post("/api/workouts/validate", dependencies=[Depends(authenticated)])
    def validate_workout(body: Workout):
        return {"ok": True}

    @app.post("/api/workouts/from-coach", dependencies=[Depends(authenticated)])
    def import_coach_workout(body: CoachWorkoutBody):
        return app.state.workouts.from_coach(body.source)

    @app.post("/api/workouts/{identifier}/remove", dependencies=[Depends(authenticated)])
    def remove_workout(identifier: str):
        return app.state.workouts.remove(identifier)

    @app.post("/api/coach/sessions/{source}/remove", dependencies=[Depends(authenticated)])
    def remove_coach_session(source: str, draft: bool = False):
        return app.state.workouts.remove_coach(source, draft)

    @app.post("/api/workouts/{identifier}", dependencies=[Depends(authenticated)])
    def edit_workout(identifier: str, body: Workout):
        app.state.workouts.get(identifier)
        return app.state.workouts.save(body, identifier)

    @app.get("/api/workouts/{identifier}", dependencies=[Depends(authenticated)])
    def get_workout(identifier: str):
        return app.state.workouts.get(identifier)

    @app.get("/api/workouts/{identifier}/preview", dependencies=[Depends(authenticated)])
    def preview_workout(identifier: str):
        return app.state.workouts.preview(identifier)

    @app.post("/api/workouts/{identifier}/send", dependencies=[Depends(authenticated)])
    def send_workout(identifier: str, body: SendWorkoutBody):
        app.state.workouts.get(identifier)
        return {
            "job_id": app.state.jobs.start(
                "garmin", lambda job: app.state.workouts.send(identifier, body.revision)
            )
        }

    @app.get("/api/workout-options", dependencies=[Depends(authenticated)])
    def workout_options():
        from garminconnect.exercises import CATEGORIES

        return {
            "strength_categories": sorted(CATEGORIES),
            "catalog": app.state.store.get("garmin_workout_catalog", {}),
        }

    return app
