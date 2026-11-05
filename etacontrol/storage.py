from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("ETA_CONTROL_DATA", ROOT / "data"))


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def uid() -> str:
    return uuid.uuid4().hex


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


class Store:
    def __init__(self, directory: Path = DATA):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db = self.directory / "eta.sqlite3"
        self.lock = threading.RLock()
        with self.connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS suppliers(plant TEXT NOT NULL, gsdb TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(plant,gsdb));
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, imported_at TEXT NOT NULL, source_at TEXT NOT NULL,
                label TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS shipments(run_id TEXT NOT NULL, id TEXT NOT NULL, plant TEXT, asn TEXT,
                supplier TEXT, payload TEXT NOT NULL, PRIMARY KEY(run_id,id));
            CREATE INDEX IF NOT EXISTS shipment_run ON shipments(run_id);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, state TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS plans(id TEXT PRIMARY KEY, run_id TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS plan_items(id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, job_id TEXT,
                level TEXT NOT NULL, message TEXT NOT NULL, payload TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get(self, key, default=None):
        with self.connect() as db:
            row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, encode(value)))

    def event(self, message, level="info", job_id=None, **payload):
        with self.connect() as db:
            db.execute("INSERT INTO events(at,job_id,level,message,payload) VALUES(?,?,?,?,?)",
                       (now(), job_id, level, message, encode(payload)))

    def events(self, limit=100, job_id=None):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM events " + ("WHERE job_id=? " if job_id else "") + "ORDER BY id DESC LIMIT ?",
                              (job_id, limit) if job_id else (limit,)).fetchall()
        return [dict(r) | {"detail": json.loads(r["payload"])} for r in rows]

    def suppliers(self):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT payload FROM suppliers ORDER BY plant,gsdb")]

    def save_suppliers(self, rows):
        with self.connect() as db:
            db.execute("DELETE FROM suppliers")
            db.executemany("INSERT INTO suppliers VALUES(?,?,?)", [(r["plant"], r["gsdb"], encode(r)) for r in rows])
        self.set("supplier_revision", uid())

    def commit_import(self, suppliers, prepared_runs, sources, empty, revision, settings=None):
        """Do?rulanan aktar?m? atomik kaydeder; hata veya iptalde mevcut kay?tlar korunur."""
        with self.connect() as db:
            db.execute("DELETE FROM suppliers")
            db.executemany("INSERT INTO suppliers VALUES(?,?,?)", [(r["plant"], r["gsdb"], encode(r)) for r in suppliers])
            for run, records in prepared_runs:
                db.execute("INSERT OR REPLACE INTO runs VALUES(?,?,?,?,?,?)", (run["id"], run["imported_at"], run["source_at"], run["label"], run["kind"], encode(run)))
                db.execute("DELETE FROM shipments WHERE run_id=?", (run["id"],))
                db.executemany("INSERT INTO shipments VALUES(?,?,?,?,?,?)", [(run["id"], r["id"], r["plant"], r["asn"], r["supplier"], encode(r)) for r in records])
            for key, value in (("supplier_revision", revision), ("sources", sources), ("empty_snapshots", empty)):
                db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (key, encode(value)))
            if settings is not None:
                db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", ("settings", encode(settings)))

    def save_run(self, run, records):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO runs VALUES(?,?,?,?,?,?)", (run["id"], run["imported_at"], run["source_at"], run["label"], run["kind"], encode(run)))
            db.execute("DELETE FROM shipments WHERE run_id=?", (run["id"],))
            db.executemany("INSERT INTO shipments VALUES(?,?,?,?,?,?)", [(run["id"], r["id"], r["plant"], r["asn"], r["supplier"], encode(r)) for r in records])

    def runs(self):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT payload FROM runs ORDER BY source_at DESC, imported_at DESC")]

    def run(self, run_id):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM runs WHERE id=?", (run_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def records(self, run_id):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT payload FROM shipments WHERE run_id=? ORDER BY plant,asn,id", (run_id,))]

    def save_job(self, job):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO jobs VALUES(?,?,?,?)", (job["id"], job["state"], job["kind"], encode(job)))

    def jobs(self):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT payload FROM jobs ORDER BY rowid DESC LIMIT 60")]

    def save_plan(self, plan, items):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO plans VALUES(?,?,?)", (plan["id"], plan["run_id"], encode(plan)))
            db.executemany("INSERT OR REPLACE INTO plan_items VALUES(?,?,?,?)", [(r["id"], plan["id"], r["status"], encode(r)) for r in items])

    def plans(self):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT payload FROM plans ORDER BY rowid DESC")]

    def plan_items(self, plan_id):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT payload FROM plan_items WHERE plan_id=? ORDER BY rowid", (plan_id,))]

    def update_item(self, item):
        with self.connect() as db:
            db.execute("UPDATE plan_items SET status=?,payload=? WHERE id=?", (item["status"], encode(item), item["id"]))

