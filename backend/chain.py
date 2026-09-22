"""Hash-chained append-only log: the only source of truth.

    event_hash(n) = SHA-256( prev_hash || stream_prev_hash || int64_be(n) || JCS(envelope) )

prev_hash and stream_prev_hash are the hex digests of the previous event in the whole
log and in this stream. JCS is RFC 8785 canonical JSON. This module is the executable
specification: the Java Command API must reproduce these digests exactly.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import struct
import threading
import uuid

import rfc8785

from . import db

ZERO = "0" * 64
ENVELOPE_FIELDS = ("event_id", "stream_id", "stream_version", "event_type", "schema_version",
                   "occurred_at", "recorded_at", "actor_id", "actor_role", "trust_level",
                   "source", "correlation_id", "causation_id", "payload", "attachments")

_write_lock = threading.Lock()      # stands in for the chain-head row lock in PostgreSQL


class Conflict(Exception):
    def __init__(self, stream_id, current_version):
        super().__init__(f"{stream_id} is at version {current_version}")
        self.stream_id, self.current_version = stream_id, current_version


def now_iso() -> str:
    t = dt.datetime.now(dt.timezone.utc)
    return t.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def iso(value) -> str:
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return value.astimezone(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return str(value)


def envelope_of(row: dict) -> dict:
    env = {}
    for k in ENVELOPE_FIELDS:
        v = row[k]
        if k in ("payload", "attachments") and isinstance(v, str):
            v = json.loads(v)
        env[k] = v
    return env


def compute_hash(prev_hash: str, stream_prev_hash: str, position: int, env: dict) -> str:
    h = hashlib.sha256()
    h.update(bytes.fromhex(prev_hash))
    h.update(bytes.fromhex(stream_prev_hash))
    h.update(struct.pack(">q", position))
    h.update(rfc8785.dumps(env))
    return h.hexdigest()


def append(conn: db.Conn, *, stream_id: str, event_type: str, payload: dict,
           actor_id: str = "system", actor_role: str = "SYSTEM",
           trust_level: str = "OFFICER_ATTESTED", source: str = "SYSTEM",
           occurred_at=None, attachments=None, expected_version: int | None = None,
           event_id: str | None = None, correlation_id=None, causation_id=None) -> dict:
    """Append one event. Idempotent on event_id, optimistic on expected_version."""
    event_id = event_id or str(uuid.uuid4())
    with _write_lock:
        existing = conn.one("SELECT * FROM es_events WHERE event_id = ?", (event_id,))
        if existing:                                   # safe retry of the same command
            existing["duplicate"] = True
            return existing

        head = conn.one("SELECT position, head_hash FROM es_chain_head WHERE singleton = 1")
        if head is None:
            conn.execute("INSERT INTO es_chain_head (singleton, position, head_hash) VALUES (1, 0, ?)",
                         (ZERO,))
            head = {"position": 0, "head_hash": ZERO}

        sh = conn.one("SELECT version, head_hash FROM es_stream_heads WHERE stream_id = ?", (stream_id,))
        s_ver, s_head = (sh["version"], sh["head_hash"]) if sh else (0, ZERO)
        if expected_version is not None and expected_version != s_ver:
            raise Conflict(stream_id, s_ver)

        row = {
            "global_position": head["position"] + 1,
            "event_id": event_id,
            "stream_id": stream_id,
            "stream_version": s_ver + 1,
            "event_type": event_type,
            "schema_version": 1,
            "occurred_at": iso(occurred_at or now_iso()),
            "recorded_at": now_iso(),
            "actor_id": actor_id,
            "actor_role": actor_role,
            "trust_level": trust_level,
            "source": source,
            "correlation_id": correlation_id,
            "causation_id": causation_id,
            "payload": json.dumps(payload, sort_keys=True),
            "attachments": json.dumps(attachments or []),
            "prev_hash": head["head_hash"],
            "stream_prev_hash": s_head,
        }
        row["event_hash"] = compute_hash(row["prev_hash"], row["stream_prev_hash"],
                                         row["global_position"], envelope_of(row))
        cols = list(row)
        conn.execute(
            f"INSERT INTO es_events ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            [row[c] for c in cols])
        conn.execute("UPDATE es_chain_head SET position = ?, head_hash = ? WHERE singleton = 1",
                     (row["global_position"], row["event_hash"]))
        if sh:
            conn.execute("UPDATE es_stream_heads SET version = ?, head_hash = ? WHERE stream_id = ?",
                         (row["stream_version"], row["event_hash"], stream_id))
        else:
            conn.execute("INSERT INTO es_stream_heads (stream_id, version, head_hash) VALUES (?, ?, ?)",
                         (stream_id, 1, row["event_hash"]))
        conn.commit()
        row["duplicate"] = False
        return row


# --------------------------------------------------------------------------- reading
def read_events(conn: db.Conn, after: int = 0, before: int | None = None,
                limit: int | None = None, types: list[str] | None = None) -> list[dict]:
    sql = "SELECT * FROM es_events WHERE global_position > ?"
    params: list = [after]
    if before is not None:
        sql += " AND global_position < ?"
        params.append(before)
    if types:
        sql += " AND event_type IN (%s)" % ", ".join("?" * len(types))
        params += types
    sql += " ORDER BY global_position"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return conn.query(sql, params)


def stream_events(conn: db.Conn, stream_id: str, as_of_position: int | None = None) -> list[dict]:
    sql = "SELECT * FROM es_events WHERE stream_id = ?"
    params: list = [stream_id]
    if as_of_position:
        sql += " AND global_position <= ?"
        params.append(as_of_position)
    return conn.query(sql + " ORDER BY stream_version", params)


def head(conn: db.Conn) -> dict:
    return conn.one("SELECT position, head_hash FROM es_chain_head WHERE singleton = 1") or {
        "position": 0, "head_hash": ZERO}


# --------------------------------------------------------------------------- checkpoints
def create_checkpoint(conn: db.Conn, reason: str = "SCHEDULED",
                      channels=("C/MLGOO e-mail", "FDP board slip", "public mirror")) -> dict:
    h = head(conn)
    if h["position"] == 0:
        raise ValueError("nothing to checkpoint yet")
    existing = conn.one("SELECT * FROM es_checkpoints WHERE position = ?", (h["position"],))
    if not existing:
        conn.execute(
            "INSERT INTO es_checkpoints (position, head_hash, created_at, reason, published_to) "
            "VALUES (?, ?, ?, ?, ?)",
            (h["position"], h["head_hash"], now_iso(), reason, json.dumps(list(channels))))
        for ch in channels:                     # copies held where the operator cannot edit them
            conn.execute(
                "INSERT OR REPLACE INTO witness_checkpoints (position, head_hash, received_at, channel) "
                "VALUES (?, ?, ?, ?)" if not db.IS_PG else
                "INSERT INTO witness_checkpoints (position, head_hash, received_at, channel) "
                "VALUES (?, ?, ?, ?) ON CONFLICT (position, channel) DO NOTHING",
                (h["position"], h["head_hash"], now_iso(), ch))
        conn.commit()
    return {"position": h["position"], "head_hash": h["head_hash"], "reason": reason}


def witness_checkpoints(conn: db.Conn) -> list[dict]:
    return conn.query("SELECT position, head_hash, MIN(received_at) AS received_at, "
                      "GROUP_CONCAT(channel) AS channel FROM witness_checkpoints "
                      "GROUP BY position, head_hash ORDER BY position")


# --------------------------------------------------------------------------- verification
def verify(conn: db.Conn, use_witness: bool = True) -> dict:
    """Recompute the chain and compare it with checkpoints held by witnesses."""
    findings: list[dict] = []
    expect, prev = 1, ZERO
    stream_heads: dict[str, tuple[int, str]] = {}
    seen: dict[int, str] = {}
    count = 0
    for row in conn.query("SELECT * FROM es_events ORDER BY global_position"):
        count += 1
        p = row["global_position"]
        if p != expect:
            findings.append({"position": p, "kind": "GAP_OR_REORDER",
                             "detail": f"expected position {expect}"})
        if row["prev_hash"] != prev:
            findings.append({"position": p, "kind": "BROKEN_LINK",
                             "detail": "prev_hash does not match the previous event"})
        s_ver, s_head = stream_heads.get(row["stream_id"], (0, ZERO))
        if row["stream_version"] != s_ver + 1 or row["stream_prev_hash"] != s_head:
            findings.append({"position": p, "kind": "BROKEN_STREAM",
                             "detail": f"{row['stream_id']} version {row['stream_version']}"})
        recomputed = compute_hash(row["prev_hash"], row["stream_prev_hash"], p, envelope_of(row))
        if recomputed != row["event_hash"]:
            findings.append({"position": p, "kind": "CONTENT_ALTERED",
                             "detail": f"{row['event_type']} on {row['stream_id']} was edited"})
        prev = row["event_hash"]
        stream_heads[row["stream_id"]] = (row["stream_version"], prev)
        seen[p] = prev
        expect = p + 1

    checkpoints = witness_checkpoints(conn) if use_witness else []
    for cp in checkpoints:
        if cp["position"] > count:
            findings.append({"position": cp["position"], "kind": "TRUNCATED",
                             "detail": f"witness holds position {cp['position']}, log ends at {count}"})
        elif seen.get(cp["position"]) != cp["head_hash"]:
            findings.append({"position": cp["position"], "kind": "CHECKPOINT_MISMATCH",
                             "detail": "history differs from the witnessed checkpoint"})
    return {
        "ok": not findings,
        "events_checked": count,
        "checkpoints_checked": len(checkpoints),
        "head_hash": prev,
        "findings": findings[:50],
        "finding_count": len(findings),
    }
