"""Persistencia local: datos deportivos en SQLite y credenciales cifradas aparte."""

import hashlib
import json
import os
import secrets
import sqlite3
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from cryptography.fernet import Fernet

from garmin_planner.planned_sessions import PlannedSessions


def private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        path.chmod(0o700)


def atomic_write(path: Path, content: bytes) -> None:
    private_dir(path.parent)
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class Vault:
    def __init__(self, root: Path):
        self.root = root / "secrets"
        private_dir(self.root)
        key = self.root / "master.key"
        if not key.exists():
            atomic_write(key, Fernet.generate_key())
        self.fernet = Fernet(key.read_bytes())

    def read(self, name: str) -> dict | None:
        path = self.root / f"{name}.enc"
        return json.loads(self.fernet.decrypt(path.read_bytes())) if path.exists() else None

    def write(self, name: str, data: dict) -> None:
        atomic_write(self.root / f"{name}.enc", self.fernet.encrypt(json.dumps(data).encode()))

    def delete(self, name: str) -> None:
        (self.root / f"{name}.enc").unlink(missing_ok=True)


class Store:
    def __init__(self, root: Path):
        private_dir(root)
        self.path = root / "planner.sqlite3"
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS coach_history (
                    id TEXT PRIMARY KEY, start TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, csrf TEXT NOT NULL, authenticated INTEGER NOT NULL,
                    expires REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS activities (
                    id TEXT PRIMARY KEY, day TEXT NOT NULL, sport TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS activity_day ON activities(day);
                CREATE TABLE IF NOT EXISTS manual_completions (
                    entry_id TEXT PRIMARY KEY, day TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS completion_day ON manual_completions(day);
                CREATE TABLE IF NOT EXISTS wellness (day TEXT PRIMARY KEY, payload TEXT NOT NULL);
            """)
            PlannedSessions.migrate(db)
        if os.name != "nt":
            self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, key: str, default=None):
        with self.connect() as db:
            return PlannedSessions.get(db, key, default)

    def set(self, key: str, value) -> None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if key in ("coach_calendar", "coach_draft"):
                PlannedSessions.set(db, key, value)
            else:
                db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, json.dumps(value)))

    def planned_sessions(self, start=None, end=None, draft=False):
        with self.connect() as db:
            return PlannedSessions.listing(db, "draft" if draft else "accepted", start, end)

    def remove_coach_session(self, source, draft=False):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            PlannedSessions.remove(db, source, draft)
        return {"ok": True}

    def setup(self, password: str) -> None:
        salt = secrets.token_bytes(16)
        digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1).hex()
        with self.connect() as db:
            db.execute(
                "INSERT INTO meta VALUES ('password', ?)",
                (json.dumps({"salt": salt.hex(), "hash": digest}),),
            )

    def check_password(self, password: str) -> bool:
        record = self.get("password")
        if not record:
            return False
        digest = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(record["salt"]), n=16384, r=8, p=1
        ).hex()
        return secrets.compare_digest(digest, record["hash"])

    def new_session(self, authenticated=False) -> tuple[str, dict]:
        sid = secrets.token_urlsafe(32)
        record = {
            "csrf": secrets.token_urlsafe(32),
            "authenticated": authenticated,
            "expires": time.time() + 43200,
        }
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
            db.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?)",
                (hashlib.sha256(sid.encode()).hexdigest(), *record.values()),
            )
        return sid, record

    def session(self, sid: str | None) -> dict | None:
        if not sid:
            return None
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM sessions WHERE id=? AND expires>?",
                (hashlib.sha256(sid.encode()).hexdigest(), time.time()),
            ).fetchone()
        return dict(row) if row else None

    def end_session(self, sid: str) -> None:
        with self.connect() as db:
            db.execute(
                "DELETE FROM sessions WHERE id=?", (hashlib.sha256(sid.encode()).hexdigest(),)
            )

    def save_activities(self, rows: list[dict], sync: dict) -> None:
        with self.connect() as db:
            for row in rows:
                db.execute(
                    "INSERT OR REPLACE INTO activities VALUES (?, ?, ?, ?)",
                    (row["id"], row["day"], row["sport"], json.dumps(row)),
                )
            db.execute("INSERT OR REPLACE INTO meta VALUES ('sync', ?)", (json.dumps(sync),))

    def activities(self, start: str, end: str, sport: str | None = None) -> list[dict]:
        query = "SELECT payload FROM activities WHERE day>=? AND day<=?"
        args = [start, end]
        if sport:
            query += " AND sport=?"
            args.append(sport)
        with self.connect() as db:
            rows = db.execute(query + " ORDER BY day DESC, id DESC", args).fetchall()
        return [json.loads(row[0]) for row in rows]

    def completions(self, start, end):
        with self.connect() as db:
            rows = db.execute(
                "SELECT entry_id,payload FROM manual_completions WHERE day>=? AND day<=?",
                (start, end),
            ).fetchall()
        return [{"entry_id": r["entry_id"], **json.loads(r["payload"])} for r in rows]

    def set_completion(self, entry_id, session, completed):
        with self.connect() as db:
            if completed:
                db.execute(
                    "INSERT INTO manual_completions VALUES (?,?,?) "
                    "ON CONFLICT(entry_id) DO NOTHING",
                    (entry_id, session["day"], json.dumps(session)),
                )
            else:
                db.execute("DELETE FROM manual_completions WHERE entry_id=?", (entry_id,))

    def training_activities(self, start, end):
        manual = [
            {
                "id": c["entry_id"],
                "day": c["day"],
                "sport": c["sport"],
                "name": c["title"],
                "duration_seconds": c["minutes"] * 60,
                "distance_m": 0,
                "elevation_m": 0,
                "origin": "manual_completion",
            }
            for c in self.completions(start, end)
        ]
        return self.activities(start, end) + manual

    def save_wellness(self, day: str, value: dict):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO wellness VALUES (?, ?)", (day, json.dumps(value)))

    def wellness(self, start: str, end: str) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT payload FROM wellness WHERE day>=? AND day<=? ORDER BY day DESC",
                (start, end),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def accept_plan(self, accepted):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            from garmin_planner.coach import fingerprint
            from garmin_planner.pro import ProError

            config = db.execute("SELECT value FROM meta WHERE key='coach_setup'").fetchone()
            draft = db.execute("SELECT value FROM meta WHERE key='coach_draft'").fetchone()
            if (
                not config
                or not draft
                or json.loads(draft[0])["id"] != accepted["id"]
                or fingerprint(json.loads(config[0])) != accepted["setup_hash"]
            ):
                raise ProError("El perfil o el borrador cambió. Revisa antes de guardar.")
            from datetime import date, timedelta

            end = (date.fromisoformat(accepted["start"]) + timedelta(days=7)).isoformat()
            db.execute(
                "UPDATE planned_sessions SET deleted=1 WHERE kind='accepted' AND "
                "deleted=0 AND day>=? AND day<?",
                (accepted["start"], end),
            )
            PlannedSessions.insert(db, accepted["plan"]["sessions"], "accepted", accepted["id"])
            db.execute("INSERT OR REPLACE INTO meta VALUES ('coach_calendar_initialized','true')")
            db.execute(
                "INSERT OR REPLACE INTO coach_history VALUES (?, ?, ?)",
                (accepted["id"], accepted["start"], json.dumps(accepted)),
            )
            for key, value in [("coach_accepted", accepted)]:
                db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, json.dumps(value)))
            db.execute("UPDATE planned_sessions SET deleted=1 WHERE kind='draft' AND deleted=0")
            db.execute("DELETE FROM meta WHERE key='coach_draft'")
