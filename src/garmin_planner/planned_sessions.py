"""Persistencia relacional de sesiones del coach y migración del formato anterior."""

import hashlib
import json
import uuid
from datetime import UTC, datetime

FIELDS = ("day", "sport", "title", "minutes", "instructions")


def source_key(session):
    return hashlib.sha256(json.dumps(session, sort_keys=True).encode()).hexdigest()


class PlannedSessions:
    @staticmethod
    def migrate(db):
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY)")
        if db.execute(
            "SELECT 1 FROM schema_migrations WHERE name='planned_sessions_v1'"
        ).fetchone():
            return
        db.execute("""CREATE TABLE planned_sessions (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('accepted','draft')),
            plan_id TEXT, source_key TEXT NOT NULL, position INTEGER NOT NULL,
            day TEXT, sport TEXT, title TEXT, minutes INTEGER,
            instructions TEXT, details TEXT NOT NULL, deleted INTEGER NOT NULL DEFAULT 0)""")
        db.execute("CREATE INDEX planned_sessions_dates ON planned_sessions(kind,deleted,day)")
        db.execute("CREATE INDEX planned_sessions_source ON planned_sessions(source_key)")
        for key in ("coach_calendar", "coach_draft"):
            row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            if row:
                db.execute(
                    "INSERT INTO meta(key,value) VALUES(?,?)", ("legacy_" + key + "_v1", row[0])
                )
                PlannedSessions.set(db, key, json.loads(row[0]))
        db.execute("INSERT INTO schema_migrations VALUES ('planned_sessions_v1')")

    @staticmethod
    def insert(db, sessions, kind, plan_id=None):
        maximum = db.execute(
            "SELECT COALESCE(MAX(position),-1) FROM planned_sessions WHERE kind=?", (kind,)
        ).fetchone()[0]
        for position, session in enumerate(sessions, maximum + 1):
            details = {k: v for k, v in session.items() if k not in FIELDS or v is None}
            db.execute(
                """INSERT INTO planned_sessions
                (id,kind,plan_id,source_key,position,day,sport,title,minutes,instructions,details)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    uuid.uuid4().hex,
                    kind,
                    plan_id,
                    source_key(session),
                    position,
                    *(session.get(field) for field in FIELDS),
                    json.dumps(details),
                ),
            )

    @staticmethod
    def listing(db, kind, start=None, end=None):
        query = "SELECT * FROM planned_sessions WHERE kind=? AND deleted=0"
        arguments = [kind]
        if start is not None:
            query += " AND day>=?"
            arguments.append(start)
        if end is not None:
            query += " AND day<=?"
            arguments.append(end)
        rows = db.execute(query + " ORDER BY position,id", arguments).fetchall()
        return [
            {
                "id": row["id"],
                "source_key": row["source_key"],
                "session": {
                    **{field: row[field] for field in FIELDS if row[field] is not None},
                    **json.loads(row["details"]),
                },
            }
            for row in rows
        ]

    @staticmethod
    def get(db, key, default=None):
        if key == "coach_calendar":
            initialized = db.execute(
                "SELECT 1 FROM meta WHERE key='coach_calendar_initialized'"
            ).fetchone()
            return (
                [item["session"] for item in PlannedSessions.listing(db, "accepted")]
                if initialized
                else default
            )
        row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        value = json.loads(row[0]) if row else default
        if key == "coach_draft" and value:
            value["plan"]["sessions"] = [
                item["session"] for item in PlannedSessions.listing(db, "draft")
            ]
        return value

    @staticmethod
    def set(db, key, value):
        kind = "draft" if key == "coach_draft" else "accepted"
        db.execute("UPDATE planned_sessions SET deleted=1 WHERE kind=? AND deleted=0", (kind,))
        if key == "coach_calendar":
            PlannedSessions.insert(db, value or [], kind)
            db.execute("INSERT OR REPLACE INTO meta VALUES ('coach_calendar_initialized','true')")
            db.execute("DELETE FROM meta WHERE key='coach_calendar'")
        else:
            value = json.loads(json.dumps(value))
            if value:
                sessions = value["plan"].pop("sessions", [])
                PlannedSessions.insert(db, sessions, kind, value.get("id"))
            db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, json.dumps(value)))

    @staticmethod
    def remove(db, source, draft=False):
        from garmin_planner.garmin import GarminError

        kind = "draft" if draft else "accepted"
        row = db.execute(
            "SELECT id FROM planned_sessions WHERE source_key=? AND kind=? "
            "AND deleted=0 ORDER BY position,id LIMIT 1",
            (source, kind),
        ).fetchone()
        if not row:
            raise GarminError("La sesión cambió o ya no está en el calendario. Actualiza la vista.")
        session = next(
            item["session"] for item in PlannedSessions.listing(db, kind) if item["id"] == row[0]
        )
        db.execute("UPDATE planned_sessions SET deleted=1 WHERE id=?", (row[0],))
        archive_row = db.execute(
            "SELECT value FROM meta WHERE key='removed_coach_sessions'"
        ).fetchone()
        archive = json.loads(archive_row[0]) if archive_row else []
        archive.append(
            {"session": session, "draft": draft, "removed_at": datetime.now(UTC).isoformat()}
        )
        db.execute(
            "INSERT OR REPLACE INTO meta VALUES ('removed_coach_sessions',?)",
            (json.dumps(archive),),
        )
