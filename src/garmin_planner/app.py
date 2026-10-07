"""Panel privado local con sesión y protección CSRF."""

import asyncio
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from importlib.resources import files
from zoneinfo import ZoneInfo

import httpx2 as httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from filelock import FileLock, Timeout
from starlette.middleware.trustedhost import TrustedHostMiddleware

from garmin_planner import __version__
from garmin_planner.api.routing import ROUTERS
from garmin_planner.api.security import COOKIE
from garmin_planner.config import Settings
from garmin_planner.garmin import GarminError, GarminService
from garmin_planner.jobs import BusyError, Jobs
from garmin_planner.library import Library
from garmin_planner.pro import ProClient, ProError
from garmin_planner.storage import Store, Vault, private_dir
from garmin_planner.workouts import Workouts


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

    app.state.start_sync = start_sync
    for build_router in ROUTERS:
        app.include_router(build_router(app, config, authenticated, session, set_cookie))
    return app
