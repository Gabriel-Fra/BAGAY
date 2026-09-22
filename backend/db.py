"""Tiny database layer that speaks SQLite (demo default) and PostgreSQL (production path).

Only one dialect difference matters here: parameter placeholders. We write SQL with
'?' and translate to '%s' for PostgreSQL. Hashes are stored as lowercase hex TEXT in
both dialects so the demo and the production schema agree byte for byte on content.
"""
from __future__ import annotations

import os
import pathlib
import sqlite3
import threading

DB_URL = os.environ.get("BAGAY_DB", "sqlite:///bagay_demo.db")
IS_PG = DB_URL.startswith("postgres")
SCHEMA = pathlib.Path(__file__).with_name("schema.sql")

_local = threading.local()


def _translate(sql: str) -> str:
    return sql.replace("?", "%s") if IS_PG else sql


class Conn:
    """Thin wrapper so the rest of the code never cares which driver is underneath."""

    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql, params=()):
        cur = self.raw.cursor()
        cur.execute(_translate(sql), tuple(params))
        return cur

    def query(self, sql, params=()) -> list[dict]:
        cur = self.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def one(self, sql, params=()) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()


def connect() -> Conn:
    if IS_PG:
        import psycopg  # imported lazily so SQLite users need no driver

        return Conn(psycopg.connect(DB_URL))
    path = DB_URL.replace("sqlite:///", "")
    raw = sqlite3.connect(path, isolation_level=None, timeout=30)
    raw.execute("PRAGMA journal_mode=WAL")
    raw.execute("PRAGMA foreign_keys=ON")
    raw.execute("BEGIN")          # keep the explicit transaction model of the real system
    raw.commit()
    return Conn(raw)


def shared() -> Conn:
    """One connection per thread, created on first use."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _local.conn = connect()
    return conn


TABLES = ("es_events", "es_chain_head", "es_stream_heads", "es_checkpoints", "witness_checkpoints",
          "proj_consumer_offsets", "proj_asset_current", "proj_asset_timeline", "proj_issue_inbox",
          "proj_work_queue", "proj_hazard_events", "proj_hazard_damage", "iam_users")


def wipe(conn: "Conn") -> None:
    """Empty every table through an existing connection (safe while the server is running)."""
    set_immutability(conn, False)
    for table in TABLES:
        try:
            conn.execute(f"DELETE FROM {table}")
        except Exception:                                  # noqa: BLE001 - table may not exist yet
            pass
    conn.commit()
    set_immutability(conn, True)


def init_db(reset: bool = False) -> None:
    if reset and not IS_PG:
        path = pathlib.Path(DB_URL.replace("sqlite:///", ""))
        for p in (path, path.with_suffix(path.suffix + "-wal"), path.with_suffix(path.suffix + "-shm")):
            p.unlink(missing_ok=True)
    conn = connect()
    sql = SCHEMA.read_text()
    if IS_PG:
        sql = (sql.replace("TEXT PRIMARY KEY", "TEXT PRIMARY KEY")
                  .replace("INTEGER PRIMARY KEY", "BIGINT PRIMARY KEY"))
    for stmt in [s.strip() for s in sql.split(";\n") if s.strip()]:
        try:
            conn.execute(stmt)
        except Exception as exc:                      # noqa: BLE001 - idempotent init
            if "already exists" not in str(exc).lower():
                raise
    conn.commit()
    conn.close()


# --------------------------------------------------------------------------- demo only
IMMUTABILITY_TRIGGERS = ["bagay_no_update", "bagay_no_delete"]


def set_immutability(conn: Conn, enabled: bool) -> None:
    """The demo's stand-in for a database superuser disabling protections.

    Production never calls this; it exists so the tamper demo can show that the hash
    chain still catches an attacker who can turn the guard rails off.
    """
    if IS_PG:
        state = "ENABLE" if enabled else "DISABLE"
        conn.execute(f"ALTER TABLE es_events {state} TRIGGER USER")
    else:
        if enabled:
            conn.execute(
                "CREATE TRIGGER IF NOT EXISTS bagay_no_update BEFORE UPDATE ON es_events "
                "BEGIN SELECT RAISE(ABORT, 'BAGAY-IMMUTABLE: events cannot be updated'); END")
            conn.execute(
                "CREATE TRIGGER IF NOT EXISTS bagay_no_delete BEFORE DELETE ON es_events "
                "BEGIN SELECT RAISE(ABORT, 'BAGAY-IMMUTABLE: events cannot be deleted'); END")
        else:
            for trg in IMMUTABILITY_TRIGGERS:
                conn.execute(f"DROP TRIGGER IF EXISTS {trg}")
    conn.commit()
