"""Trabajos en memoria y coordinación de MFA, sin almacenar contraseñas."""

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from garmin_planner.garmin import GarminError
from garmin_planner.pro import ProError


class BusyError(Exception):
    pass


class Jobs:
    def __init__(self):
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="planner")
        self.items = {}
        self.active = {}

    def start(self, kind: str, action):
        with self.lock:
            if kind in self.active:
                raise BusyError("Ya hay una operación en curso. Espera a que termine.")
            identifier = uuid.uuid4().hex
            self.items[identifier] = {
                "id": identifier,
                "kind": kind,
                "status": "running",
                "message": "Iniciando…",
                "created": time.time(),
            }
            self.active[kind] = identifier
            # Retener solo los últimos trabajos terminales, además de los activos.
            terminal = [k for k, v in self.items.items() if v["status"] in ("completed", "failed")]
            for old in terminal[:-20]:
                del self.items[old]

        def run():
            try:
                result = action(identifier)
                self.update(
                    identifier, status="completed", message="Operación completada", result=result
                )
            except (GarminError, ProError, BusyError) as exc:
                self.update(identifier, status="failed", message=str(exc))
            except Exception:
                self.update(
                    identifier,
                    status="failed",
                    message=(
                        "No se pudo completar la operación. Comprueba la conexión "
                        "y vuelve a autorizar "
                        "la cuenta si es necesario. No se han expuesto detalles de credenciales."
                    ),
                )
            finally:
                with self.lock:
                    self.active.pop(kind, None)
                    item = self.items[identifier]
                    item.pop("mfa_event", None)
                    item.pop("mfa_code", None)

        self.executor.submit(run)
        return identifier

    def update(self, identifier, **values):
        with self.lock:
            self.items[identifier].update(values)

    def get(self, identifier):
        with self.lock:
            item = self.items.get(identifier)
            return {k: v for k, v in item.items() if not k.startswith("mfa_")} if item else None

    def prompt_mfa(self, identifier):
        event = threading.Event()
        self.update(
            identifier,
            status="waiting_mfa",
            message="Introduce el código MFA de Garmin",
            mfa_event=event,
        )
        if not event.wait(180):
            raise GarminError("El código MFA ha caducado. Vuelve a conectar Garmin.")
        with self.lock:
            item = self.items[identifier]
            code = item.pop("mfa_code", "")
            item["status"] = "running"
        if not code:
            raise GarminError("La autenticación se ha cancelado.")
        return code

    def submit_mfa(self, identifier, code):
        with self.lock:
            item = self.items.get(identifier)
            if not item or item["status"] != "waiting_mfa" or "mfa_code" in item:
                raise GarminError("No hay una solicitud MFA pendiente.")
            item["mfa_code"] = code
            item["mfa_event"].set()

    def close(self):
        with self.lock:
            for item in self.items.values():
                if item.get("mfa_event"):
                    item["mfa_event"].set()
        self.executor.shutdown(wait=True, cancel_futures=True)
