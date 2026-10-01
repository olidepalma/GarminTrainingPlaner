"""Sesiones por bloques, conversión Garmin y publicación explícita sin reintentos."""

import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from typing import Literal

from garminconnect.workout import ConditionType, SportType, StepType, TargetType
from pydantic import BaseModel, ConfigDict, Field, model_validator

from garmin_planner.garmin import GarminError


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Block(Strict):
    kind: Literal["warmup", "exercise", "recovery", "rest", "cooldown", "repeat"] = "exercise"
    duration_type: Literal["time", "distance", "lap", "reps"] = "time"
    value: float | None = Field(default=None, gt=0, le=86400, allow_inf_nan=False)
    target: Literal["none", "hr_zone", "power_zone"] = "none"
    zone: int | None = Field(default=None, ge=1, le=7)
    stroke: str = Field(default="", max_length=80)
    equipment: str = Field(default="", max_length=80)
    notes: str = Field(default="", max_length=500)
    category: str = Field(default="", max_length=80)
    iterations: int = Field(default=1, ge=1, le=50)
    steps: list["Block"] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def valid(self):
        if self.kind == "repeat":
            if not self.steps or self.iterations < 2:
                raise ValueError("Un bloque repetido necesita al menos dos repeticiones y un paso")
            if self.value is not None or self.target != "none" or self.zone is not None:
                raise ValueError("Configura duración y objetivos dentro de los pasos repetidos")
        else:
            if self.steps or self.iterations != 1:
                raise ValueError("Solo los bloques de repetición tienen pasos y repeticiones")
            if self.duration_type != "lap" and self.value is None:
                raise ValueError("Indica la duración del paso en segundos, metros o repeticiones")
            if self.duration_type == "lap" and self.value is not None:
                raise ValueError("El paso hasta pulsar Lap no lleva duración numérica")
            if self.target == "none" and self.zone is not None:
                raise ValueError("Un paso sin objetivo no debe indicar zona")
            if self.target != "none" and self.zone is None:
                raise ValueError("Selecciona la zona del objetivo")
            if self.target == "hr_zone" and self.zone > 5:
                raise ValueError("La zona de frecuencia cardiaca debe estar entre 1 y 5")
        return self


class Structure(Strict):
    pool_length: int = Field(default=25, ge=5, le=150)
    blocks: list[Block] = Field(min_length=1, max_length=30)


class Workout(Strict):
    title: str = Field(min_length=1, max_length=100)
    day: date
    sport: Literal["running", "trail", "cycling", "swimming", "strength"]
    minutes: int = Field(ge=1, le=480)
    instructions: str = Field(default="", max_length=2500)
    structure: Structure

    @model_validator(mode="after")
    def validate_structure(self):
        validate_structure(self.structure, self.sport, self.minutes)
        return self


def validate_structure(structure, sport, minutes):
    from garminconnect.exercises import CATEGORIES

    counts = 0

    def walk(block, depth=0, multiplier=1):
        nonlocal counts
        counts += 1
        if counts > 50 or depth > 2:
            raise ValueError("Máximo 50 pasos y dos niveles de repetición")
        if multiplier * block.iterations > 500:
            raise ValueError("Demasiadas repeticiones en la sesión")
        if block.kind == "repeat":
            values = [
                walk(child, depth + 1, multiplier * block.iterations) for child in block.steps
            ]
            return sum(v[0] for v in values) * block.iterations, all(v[1] for v in values)
        if (block.stroke or block.equipment) and sport != "swimming":
            raise ValueError("Estilo y material de natación solo se admiten en natación")
        if block.duration_type == "reps":
            if sport != "strength" or not block.category or block.category not in CATEGORIES:
                raise ValueError("Las repeticiones necesitan fuerza y una categoría Garmin válida")
            if block.value != int(block.value):
                raise ValueError("Las repeticiones deben ser enteras")
        if block.category and sport != "strength":
            raise ValueError("La categoría de ejercicio solo se utiliza en fuerza")
        if block.target == "power_zone" and sport != "cycling":
            raise ValueError("Las zonas de potencia se admiten para ciclismo")
        if sport == "swimming":
            if block.target != "none":
                raise ValueError(
                    "En natación usa estilo y notas, sin zonas cardiacas o de potencia"
                )
            if block.duration_type == "distance" and block.value % structure.pool_length:
                raise ValueError("La distancia de piscina debe ser múltiplo de su longitud")
        return (block.value if block.duration_type == "time" else 0), block.duration_type == "time"

    for block in structure.blocks:
        walk(block)


def duration_warnings(structure, minutes):
    def total(block):
        if block.kind == "repeat":
            children = [total(child) for child in block.steps]
            return sum(t for t, _ in children) * block.iterations, all(v for _, v in children)
        return (block.value if block.duration_type == "time" else 0), block.duration_type == "time"

    totals = [total(block) for block in structure.blocks]
    seconds = sum(t for t, _ in totals)
    if seconds != minutes * 60 and (all(v for _, v in totals) or seconds > minutes * 60):
        return [
            f"Los bloques por tiempo suman {int(seconds // 60)}:{int(seconds % 60):02d}, "
            f"y la duración estimada es {minutes} min. Puedes guardar y enviar la sesión "
            "sin cambiar ninguno de los dos valores."
        ]
    return []


SPORTS = {
    "running": (SportType.RUNNING, "running"),
    "trail": (SportType.RUNNING, "running"),
    "cycling": (SportType.CYCLING, "cycling"),
    "swimming": (SportType.SWIMMING, "swimming"),
    "strength": (SportType.STRENGTH_TRAINING, "strength_training"),
}


def garmin_payload(workout, catalog=None):
    catalog = catalog or VERIFIED_CATALOG
    sport_id, sport_key = SPORTS[workout.sport]
    sport = {"sportTypeId": sport_id, "sportTypeKey": sport_key}
    order = 0

    def convert(block):
        nonlocal order
        order += 1
        current = order
        if block.kind == "repeat":
            return {
                "type": "RepeatGroupDTO",
                "stepOrder": current,
                "stepType": {"stepTypeId": StepType.REPEAT, "stepTypeKey": "repeat"},
                "numberOfIterations": block.iterations,
                "endCondition": {
                    "conditionTypeId": ConditionType.ITERATIONS,
                    "conditionTypeKey": "iterations",
                },
                "endConditionValue": block.iterations,
                "smartRepeat": False,
                "workoutSteps": [convert(s) for s in block.steps],
            }
        kind_id, kind_key = {
            "warmup": (StepType.WARMUP, "warmup"),
            "exercise": (StepType.INTERVAL, "interval"),
            "recovery": (StepType.RECOVERY, "recovery"),
            "rest": (StepType.REST, "rest"),
            "cooldown": (StepType.COOLDOWN, "cooldown"),
        }[block.kind]
        condition_id, condition_key = {
            "time": (ConditionType.TIME, "time"),
            "distance": (ConditionType.DISTANCE, "distance"),
            "lap": (ConditionType.LAP_BUTTON, "lap.button"),
            "reps": (ConditionType.REPS, "reps"),
        }[block.duration_type]
        target_id, target_key = {
            "none": (TargetType.NO_TARGET, "no.target"),
            "hr_zone": (TargetType.HEART_RATE_ZONE, "heart.rate.zone"),
            "power_zone": (TargetType.POWER_ZONE, "power.zone"),
        }[block.target]
        notes = block.notes
        row = {
            "type": "ExecutableStepDTO",
            "stepOrder": current,
            "stepType": {"stepTypeId": kind_id, "stepTypeKey": kind_key},
            "endCondition": {"conditionTypeId": condition_id, "conditionTypeKey": condition_key},
            "endConditionValue": block.value,
            "targetType": {"workoutTargetTypeId": target_id, "workoutTargetTypeKey": target_key},
            "zoneNumber": block.zone,
        }
        for field, choice in (("strokeType", block.stroke), ("equipmentType", block.equipment)):
            if choice:
                verified = catalog.get(field, {}).get(choice)
                if verified:
                    row[field] = verified
                else:
                    # No inventar IDs de la interfaz Garmin. El dato se conserva en las notas.
                    notes = (notes + " · " if notes else "") + choice
        row["description"] = notes
        if block.category:
            row["category"] = block.category
            row["exerciseName"] = ""
        return row

    result = {
        "workoutName": workout.title,
        "sportType": sport,
        "description": workout.instructions,
        "estimatedDurationInSecs": workout.minutes * 60,
        "workoutSegments": [
            {
                "segmentOrder": 1,
                "sportType": sport,
                "workoutSteps": [convert(b) for b in workout.structure.blocks],
            }
        ],
    }
    if workout.sport == "swimming":
        result.update(
            poolLength=workout.structure.pool_length,
            poolLengthUnit={"unitId": 1, "unitKey": "meter"},
        )
    return result


VERIFIED_CATALOG = {
    "strokeType": {
        "free": {"strokeTypeId": 6, "strokeTypeKey": "free", "displayOrder": 6},
        "backstroke": {"strokeTypeId": 2, "strokeTypeKey": "backstroke", "displayOrder": 2},
        "breaststroke": {"strokeTypeId": 3, "strokeTypeKey": "breaststroke", "displayOrder": 3},
        "any_stroke": {"strokeTypeId": 1, "strokeTypeKey": "any_stroke", "displayOrder": 1},
    },
    "equipmentType": {
        "kickboard": {"equipmentTypeId": 2, "equipmentTypeKey": "kickboard", "displayOrder": 2},
        "pull_buoy": {"equipmentTypeId": 4, "equipmentTypeKey": "pull_buoy", "displayOrder": 4},
    },
}


class Workouts:
    def __init__(self, store, garmin):
        self.store, self.garmin = store, garmin
        with store.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS workouts (
                id TEXT PRIMARY KEY, day TEXT NOT NULL, payload TEXT NOT NULL,
                publication TEXT NOT NULL DEFAULT '{}', source TEXT UNIQUE)""")
            columns = {row["name"] for row in db.execute("PRAGMA table_info(workouts)")}
            if "source" not in columns:
                db.execute("ALTER TABLE workouts ADD COLUMN source TEXT")
            if "deleted" not in columns:
                db.execute("ALTER TABLE workouts ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS workouts_source ON workouts(source)")

    def list(self, start, end):
        with self.store.connect() as db:
            rows = db.execute(
                "SELECT id,payload,publication FROM workouts WHERE day>=? AND day<=? AND source "
                "IS NULL AND deleted=0 ORDER BY day,id",
                (start, end),
            ).fetchall()
        return [
            {"id": r["id"], **json.loads(r["payload"]), "publication": json.loads(r["publication"])}
            for r in rows
        ]

    def get(self, identifier):
        with self.store.connect() as db:
            row = db.execute(
                "SELECT * FROM workouts WHERE id=? AND deleted=0", (identifier,)
            ).fetchone()
        if not row:
            raise GarminError("Sesión no encontrada")
        return {
            "id": identifier,
            **json.loads(row["payload"]),
            "publication": json.loads(row["publication"]),
        }

    def save(self, workout, identifier=None):
        payload = workout.model_dump(mode="json")
        identifier = identifier or uuid.uuid4().hex
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT publication FROM workouts WHERE id=?", (identifier,)
            ).fetchone()
            if old and json.loads(old[0]):
                raise GarminError(
                    "Esta sesión ya tiene un envío Garmin. Duplica para crear una variante; no se "
                    "modifica la sesión remota."
                )
            db.execute(
                "INSERT INTO workouts(id,day,payload) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE "
                "SET day=excluded.day,payload=excluded.payload",
                (identifier, str(workout.day), json.dumps(payload)),
            )
        return {"id": identifier, "warnings": duration_warnings(workout.structure, workout.minutes)}

    def remove(self, identifier):
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT publication FROM workouts WHERE id=? AND deleted=0", (identifier,)
            ).fetchone()
            if not row:
                raise GarminError("La sesión ya no está en el calendario")
            publication = json.loads(row["publication"])
            if publication.get("status") in ("uncertain", "uploaded", "schedule_uncertain"):
                raise GarminError(
                    "El envío Garmin está pendiente o incierto. Revísalo antes de borrar la sesión."
                )
            db.execute("UPDATE workouts SET deleted=1 WHERE id=?", (identifier,))
        return {"ok": True}

    def remove_coach(self, source, draft=False):
        key = "coach_draft" if draft else "coach_calendar"
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            value = json.loads(row["value"]) if row else None
            sessions = value["plan"]["sessions"] if draft and value else value or []
            session = next((s for s in sessions if session_key(s) == source), None)
            if not session:
                raise GarminError(
                    "La sesión cambió o ya no está en el calendario. Actualiza la vista."
                )
            sessions.remove(session)
            if draft:
                value["plan"]["sessions"] = sessions
            else:
                value = sessions
            archive_row = db.execute(
                "SELECT value FROM meta WHERE key='removed_coach_sessions'"
            ).fetchone()
            archive = json.loads(archive_row["value"]) if archive_row else []
            archive.append(
                {"session": session, "draft": draft, "removed_at": datetime.now(UTC).isoformat()}
            )
            db.execute(
                "INSERT INTO meta(key,value) VALUES('removed_coach_sessions',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (json.dumps(archive),),
            )
            db.execute("UPDATE meta SET value=? WHERE key=?", (json.dumps(value), key))
        return {"ok": True}

    def from_coach(self, source):
        sessions = self.store.get("coach_calendar", [])
        session = next((s for s in sessions if session_key(s) == source), None)
        if not session:
            raise GarminError("La sesión del coach cambió. Actualiza el calendario.")
        if not session.get("workout"):
            raise GarminError(
                "Esta sesión anterior no tiene bloques. Crea una copia y revísala en el editor."
            )
        workout = Workout.model_validate(
            {
                "title": session["title"],
                "day": session["day"],
                "sport": session["sport"],
                "minutes": session["minutes"],
                "instructions": session["instructions"],
                "structure": session["workout"],
            }
        )
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT id FROM workouts WHERE source=?", (source,)).fetchone()
            if old:
                return {"id": old[0]}
            identifier = uuid.uuid4().hex
            db.execute(
                "INSERT INTO workouts(id,day,payload,source) VALUES(?,?,?,?)",
                (identifier, str(workout.day), workout.model_dump_json(), source),
            )
        return {"id": identifier}

    def preview(self, identifier):
        saved = self.get(identifier)
        workout = Workout.model_validate(
            {k: v for k, v in saved.items() if k not in ("id", "publication")}
        )
        payload = garmin_payload(workout, self.store.get("garmin_workout_catalog", {}))
        digest = hashlib.sha256(json.dumps(saved, sort_keys=True).encode()).hexdigest()
        warnings = duration_warnings(workout.structure, workout.minutes)
        if workout.sport == "swimming":
            warnings.append(
                "Estilos o materiales sin identificador Garmin verificado se conservan en "
                "notas. Comprueba su representación en Connect antes de enviarlo al reloj."
            )
        return {
            "payload": payload,
            "revision": digest,
            "warnings": warnings,
            "day": str(workout.day),
        }

    def _publication(self, identifier, value):
        with self.store.connect() as db:
            db.execute(
                "UPDATE workouts SET publication=? WHERE id=?", (json.dumps(value), identifier)
            )

    def send(self, identifier, revision):
        preview = self.preview(identifier)
        if preview["revision"] != revision:
            raise GarminError("La sesión cambió. Revisa de nuevo la vista previa.")
        saved = self.get(identifier)
        publication = saved["publication"]
        if publication.get("status") == "complete":
            return {"ok": True, "already_sent": True, **publication}
        if publication.get("status") == "uncertain":
            raise GarminError(
                "Garmin no confirmó el envío anterior. Revisa tu biblioteca Garmin antes de "
                "duplicar o reintentar; no se repite automáticamente."
            )
        client = self.garmin.workout_client()
        if not publication.get("workout_id"):
            # Reservar la versión revisada de forma atómica antes de escribir fuera.
            with self.store.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT payload,publication FROM workouts WHERE id=? AND deleted=0",
                    (identifier,),
                ).fetchone()
                if not row:
                    raise GarminError("La sesión se borró antes del envío")
                current = {
                    "id": identifier,
                    **json.loads(row["payload"]),
                    "publication": json.loads(row["publication"]),
                }
                if (
                    hashlib.sha256(json.dumps(current, sort_keys=True).encode()).hexdigest()
                    != revision
                ):
                    raise GarminError("La sesión cambió durante la conexión. Revisa de nuevo.")
                db.execute(
                    "UPDATE workouts SET publication=? WHERE id=?",
                    (json.dumps({"status": "uncertain"}), identifier),
                )
            publication = {"status": "uncertain", "at": datetime.now(UTC).isoformat()}
            self._publication(identifier, publication)
            try:
                created = client.upload_workout(preview["payload"])
                workout_id = created.get("workoutId")
                if (
                    not isinstance(workout_id, (int, str))
                    or not str(workout_id).isdigit()
                    or int(workout_id) <= 0
                ):
                    raise ValueError("Missing workout ID")
                publication.update(status="uploaded", workout_id=str(workout_id))
                self._publication(identifier, publication)
            except Exception as exc:
                raise GarminError(
                    "Garmin no confirmó la creación. Revisa su biblioteca; se ha bloqueado el "
                    "reenvío para evitar duplicados."
                ) from exc
        if publication.get("status") == "schedule_uncertain":
            raise GarminError(
                "La programación no se confirmó. Revisa el calendario Garmin; no se repite "
                "automáticamente."
            )
        publication["status"] = "schedule_uncertain"
        self._publication(identifier, publication)
        try:
            client.schedule_workout(publication["workout_id"], saved["day"])
        except Exception as exc:
            raise GarminError(
                "La sesión se creó en Garmin, pero no se confirmó su fecha. Revisa el "
                "calendario Garmin antes de volver a programarla."
            ) from exc
        publication["status"] = "complete"
        self._publication(identifier, publication)
        return {"ok": True, **publication}


def session_key(session):
    return hashlib.sha256(json.dumps(session, sort_keys=True).encode()).hexdigest()
