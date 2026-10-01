"""Conexión Garmin y sincronización incremental; escritura de sesiones explícita."""

import json
import logging
import math
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from garminconnect import Garmin

from garmin_planner.config import Settings
from garmin_planner.sports_data import sync_references
from garmin_planner.storage import Store, Vault


class GarminError(Exception):
    pass


def number(value, default=0):
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else default
    except (TypeError, ValueError):
        return default


def normalize(raw: dict, timezone: str) -> dict:
    timestamp = raw.get("startTimeGMT")
    if timestamp:
        moment = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        day = moment.astimezone(ZoneInfo(timezone)).date()
    else:
        day = date.fromisoformat(str(raw["startTimeLocal"])[:10])
    kind = raw.get("activityType", {}).get("typeKey", "other")
    if "trail" in kind:
        sport = "trail"
    elif "running" in kind:
        sport = "running"
    elif "cycling" in kind or "biking" in kind:
        sport = "cycling"
    elif "swimming" in kind:
        sport = "swimming"
    elif "strength" in kind:
        sport = "strength"
    elif "multi_sport" in kind or "triathlon" in kind:
        sport = "triathlon"
    else:
        sport = "other"
    return {
        "id": str(raw["activityId"]),
        "day": day.isoformat(),
        "name": str(raw.get("activityName", "Actividad"))[:300],
        "sport": sport,
        "type": kind,
        "duration_seconds": number(raw.get("duration")),
        "distance_m": number(raw.get("distance")),
        "elevation_m": number(raw.get("elevationGain")),
        "average_hr": number(raw.get("averageHR"), None),
    }


class GarminService:
    def __init__(self, settings: Settings, store: Store, vault: Vault, factory=Garmin):
        self.settings, self.store, self.vault = settings, store, vault
        self.factory = factory
        # El cliente de terceros puede registrar detalles personales al fallar.
        for name in ("garminconnect", "garminconnect.client"):
            logger = logging.getLogger(name)
            logger.addHandler(logging.NullHandler())
            logger.propagate = False

    def status(self):
        connection = self.vault.read("garmin")
        return {
            "status": "connected" if connection else "not_connected",
            "name": connection.get("name") if connection else None,
            "sync": self.store.get("sync"),
            "last_attempt": self.store.get("sync_attempt"),
        }

    def connect(self, email: str, password: str, prompt_mfa):
        client = self.factory(email, password, prompt_mfa=prompt_mfa, retry_attempts=1)
        try:
            client.login()
            identity = client.display_name
            if not identity:
                raise GarminError("Garmin no devolvió una identidad válida.")
            previous = self.store.get("garmin_identity")
            if previous and previous != identity:
                raise GarminError(
                    "Los datos locales pertenecen a otra cuenta Garmin. "
                    "Usa otra carpeta GTP_DATA_DIR."
                )
            self.store.set("garmin_identity", identity)
            self.vault.write(
                "garmin",
                {
                    "name": client.full_name or "Cuenta Garmin",
                    "identity": identity,
                    "tokens": json.loads(client.client.dumps()),
                },
            )
            self.store.set("sync_attempt", None)
        finally:
            client.password = None
            client.username = None

    def workout_client(self):
        connection = self.vault.read("garmin")
        if not connection:
            raise GarminError("Conecta Garmin antes de enviar una sesión.")
        try:
            client = self.factory(retry_attempts=1)
            client.login(json.dumps(connection["tokens"]))
            if client.display_name != connection["identity"]:
                raise GarminError("La sesión Garmin corresponde a otra cuenta.")
            return client
        except GarminError:
            raise
        except Exception as exc:
            raise GarminError("No se pudo iniciar sesión en Garmin. Revisa la conexión.") from exc

    def sync(self, report=lambda message: None):
        connection = self.vault.read("garmin")
        if not connection:
            raise GarminError("Conecta Garmin antes de sincronizar.")
        client = self.factory(retry_attempts=1)
        client.login(json.dumps(connection["tokens"]))
        if client.display_name != connection["identity"]:
            raise GarminError("La sesión Garmin corresponde a otra cuenta.")
        today = datetime.now(ZoneInfo(self.settings.timezone)).date()
        previous = self.store.get("sync")
        start = (
            date.fromisoformat(previous["through"]) - timedelta(days=7)
            if previous
            else today - timedelta(days=self.settings.initial_days - 1)
        )
        # La fecha de Garmin es local; ampliamos un día para conversiones de zona.
        report("Descargando actividades recientes…")
        try:
            raw = client.get_activities_by_date(
                (start - timedelta(days=1)).isoformat(), today.isoformat()
            )
            rows = [normalize(activity, self.settings.timezone) for activity in raw]
            rows = [row for row in rows if start.isoformat() <= row["day"] <= today.isoformat()]
            sync = {
                "at": datetime.now(UTC).isoformat(),
                "through": today.isoformat(),
                "from": start.isoformat(),
                "received": len(rows),
            }
            self.store.save_activities(rows, sync)
            options = self.store.get("wellness_options", {"sleep": False, "hrv": False})
            warnings = []
            report("Actualizando recuperación de los últimos siete días…")
            for offset in range(7):
                day = (today - timedelta(days=offset)).isoformat()
                value = {
                    "day": day,
                    "steps": None,
                    "resting_hr": None,
                    "sleep_seconds": None,
                    "sleep_score": None,
                    "hrv_ms": None,
                }
                try:
                    stats = client.get_stats(day) or {}
                    value["steps"] = number(stats.get("totalSteps"), None)
                    value["resting_hr"] = number(stats.get("restingHeartRate"), None)
                except Exception:
                    warnings.append("Faltan algunos datos diarios de Garmin.")
                if options["sleep"]:
                    try:
                        sleep = (client.get_sleep_data(day) or {}).get("dailySleepDTO", {})
                        value["sleep_seconds"] = number(sleep.get("sleepTimeSeconds"), None)
                        value["sleep_score"] = number(
                            sleep.get("sleepScores", {}).get("overall", {}).get("value"), None
                        )
                    except Exception:
                        warnings.append("Garmin no devolvió algunos datos de sueño.")
                if options["hrv"]:
                    try:
                        hrv = (client.get_hrv_data(day) or {}).get("hrvSummary", {})
                        value["hrv_ms"] = number(hrv.get("lastNightAvg"), None)
                    except Exception:
                        warnings.append("Garmin no devolvió algunos datos de HRV.")
                self.store.save_wellness(day, value)
            report("Actualizando zonas, umbrales y pronósticos Garmin…")
            warnings.extend(sync_references(client, self.store, today))
            outcome = {
                "at": datetime.now(UTC).isoformat(),
                "status": "completed",
                "warnings": sorted(set(warnings)),
            }
            self.store.set("sync_attempt", outcome)
            return {**sync, **outcome}
        finally:
            # Incluye cualquier renovación durante las peticiones, sin tokens en disco sin cifrar.
            connection["tokens"] = json.loads(client.client.dumps())
            self.vault.write("garmin", connection)


def dashboard(store: Store, timezone: str, days=28, sport=None):
    today = datetime.now(ZoneInfo(timezone)).date()
    start = today - timedelta(days=days - 1)
    rows = store.activities(start.isoformat(), today.isoformat(), sport)
    groups, weeks = {}, {}
    monday = start - timedelta(days=start.weekday())
    while monday <= today:
        weeks[monday.isoformat()] = {"week": monday.isoformat(), "hours": 0, "sessions": 0}
        monday += timedelta(days=7)
    for row in rows:
        group = groups.setdefault(
            row["sport"], {"sport": row["sport"], "hours": 0, "distance_km": 0, "sessions": 0}
        )
        group["hours"] += row["duration_seconds"] / 3600
        group["distance_km"] += row["distance_m"] / 1000
        group["sessions"] += 1
        day = date.fromisoformat(row["day"])
        week = weeks[(day - timedelta(days=day.weekday())).isoformat()]
        week["hours"] += row["duration_seconds"] / 3600
        week["sessions"] += 1
    options = store.get("wellness_options", {"sleep": False, "hrv": False})
    wellness = store.wellness((today - timedelta(days=6)).isoformat(), today.isoformat())
    for row in wellness:
        if not options["sleep"]:
            row["sleep_seconds"] = row["sleep_score"] = None
        if not options["hrv"]:
            row["hrv_ms"] = None
    return {
        "from": start.isoformat(),
        "through": today.isoformat(),
        "totals": {
            "sessions": len(rows),
            "hours": sum(r["duration_seconds"] for r in rows) / 3600,
            "distance_km": sum(r["distance_m"] for r in rows) / 1000,
            "elevation_m": sum(r["elevation_m"] for r in rows),
        },
        "sports": list(groups.values()),
        "weeks": list(weeks.values()),
        "activities": rows,
        "wellness": wellness,
        "wellness_options": options,
    }
