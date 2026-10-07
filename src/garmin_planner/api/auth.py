"""Rutas de auth."""

import sqlite3
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from garmin_planner.api.schemas import PasswordBody
from garmin_planner.api.security import COOKIE


def build_router(app, config, authenticated, session, set_cookie):
    router = APIRouter()
    login_attempts = []
    login_lock = threading.Lock()

    @router.get("/api/session")
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

    @router.post("/api/session/login")
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

    @router.post("/api/session/logout")
    def logout(request: Request, record=Depends(authenticated)):
        app.state.store.end_session(request.cookies[COOKIE])
        response = JSONResponse({"ok": True})
        response.delete_cookie(COOKIE)
        return response

    return router
