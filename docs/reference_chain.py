"""
BAGAY reference implementation of the hash-chained event log.

This is the executable specification that the Java Command API and the Python
verifier must both agree with. It is intentionally small.

    event_hash = SHA-256( prev_hash
                        || stream_prev_hash
                        || int64_be(global_position)
                        || JCS(envelope) )

JCS = JSON Canonicalization Scheme, RFC 8785.
"""
from __future__ import annotations

import hashlib
import json
import struct
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

import rfc8785

ZERO = bytes(32)

# Fields covered by the hash (everything except the hashes themselves).
ENVELOPE_FIELDS = (
    "event_id", "stream_id", "stream_version", "event_type", "schema_version",
    "occurred_at", "recorded_at", "actor_id", "actor_role", "trust_level",
    "source", "correlation_id", "causation_id", "payload", "attachments",
)


def iso(ts: datetime) -> str:
    """UTC, millisecond precision, 'Z' suffix: one spelling per instant."""
    return ts.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def envelope_of(row: dict[str, Any]) -> dict[str, Any]:
    env = {k: row[k] for k in ENVELOPE_FIELDS}
    for k in ("occurred_at", "recorded_at"):
        if isinstance(env[k], datetime):
            env[k] = iso(env[k])
    for k in ("event_id", "correlation_id", "causation_id"):
        if env[k] is not None:
            env[k] = str(env[k])
    env["attachments"] = list(env["attachments"] or [])
    return env


def compute_hash(prev_hash: bytes, stream_prev_hash: bytes, position: int, env: dict) -> bytes:
    h = hashlib.sha256()
    h.update(prev_hash)
    h.update(stream_prev_hash)
    h.update(struct.pack(">q", position))
    h.update(rfc8785.dumps(env))
    return h.digest()


# ---------------------------------------------------------------------------
# Append (what the Command API does inside one transaction)
# ---------------------------------------------------------------------------
@dataclass
class NewEvent:
    stream_id: str
    event_type: str
    payload: dict
    actor_id: str = "system"
    actor_role: str = "SYSTEM"
    trust_level: str = "OFFICER_ATTESTED"
    source: str = "SYSTEM"
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    attachments: list[str] = field(default_factory=list)
    expected_version: int | None = None      # optimistic concurrency
    event_id: uuid.UUID = field(default_factory=uuid.uuid4)  # UUIDv7 in production
    correlation_id: uuid.UUID | None = None
    causation_id: uuid.UUID | None = None
    schema_version: int = 1


def append(conn, ev: NewEvent) -> dict:
    with conn.transaction():
        cur = conn.cursor()
        cur.execute("SELECT position, head_hash FROM es.chain_head WHERE singleton FOR UPDATE")
        pos, head = cur.fetchone()
        cur.execute("SELECT version, head_hash FROM es.stream_heads WHERE stream_id = %s FOR UPDATE",
                    (ev.stream_id,))
        r = cur.fetchone()
        s_ver, s_head = (r if r else (0, ZERO))
        if ev.expected_version is not None and ev.expected_version != s_ver:
            raise RuntimeError(f"conflict on {ev.stream_id}: at {s_ver}, expected {ev.expected_version}")
        # Truncate to milliseconds so the stored timestamp and the hashed string agree.
        now = datetime.now(timezone.utc)
        now = now.replace(microsecond=now.microsecond // 1000 * 1000)
        occ = ev.occurred_at.replace(microsecond=ev.occurred_at.microsecond // 1000 * 1000)
        row = dict(
            global_position=pos + 1, event_id=ev.event_id, stream_id=ev.stream_id,
            stream_version=s_ver + 1, event_type=ev.event_type, schema_version=ev.schema_version,
            occurred_at=occ, recorded_at=now, actor_id=ev.actor_id,
            actor_role=ev.actor_role, trust_level=ev.trust_level, source=ev.source,
            correlation_id=ev.correlation_id, causation_id=ev.causation_id,
            payload=ev.payload, attachments=ev.attachments,
            prev_hash=bytes(head), stream_prev_hash=bytes(s_head),
        )
        row["event_hash"] = compute_hash(row["prev_hash"], row["stream_prev_hash"],
                                         row["global_position"], envelope_of(row))
        cols = list(row)
        vals = [json.dumps(v) if k == "payload" else v for k, v in row.items()]
        cur.execute(
            f"INSERT INTO es.events ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})", vals)
        return row


# ---------------------------------------------------------------------------
# Verify (what an incoming administration runs)
# ---------------------------------------------------------------------------
@dataclass
class Finding:
    position: int
    kind: str
    detail: str


def iter_events(conn) -> Iterable[dict]:
    cur = conn.cursor()
    cur.execute("SELECT * FROM es.events ORDER BY global_position")
    names = [d.name for d in cur.description]
    for rec in cur:
        yield dict(zip(names, rec))


def verify(conn, checkpoints: list[tuple[int, bytes]] | None = None) -> list[Finding]:
    """Recompute the chain. `checkpoints` are (position, head_hash) pairs obtained
    from an EXTERNAL witness, never from the database being verified."""
    findings: list[Finding] = []
    expect_pos, prev = 1, ZERO
    stream_heads: dict[str, tuple[int, bytes]] = {}
    seen: dict[int, bytes] = {}
    for row in iter_events(conn):
        p = row["global_position"]
        if p != expect_pos:
            findings.append(Finding(p, "GAP_OR_REORDER", f"expected position {expect_pos}"))
        if bytes(row["prev_hash"]) != prev:
            findings.append(Finding(p, "BROKEN_LINK", "prev_hash does not match previous event_hash"))
        s_ver, s_head = stream_heads.get(row["stream_id"], (0, ZERO))
        if row["stream_version"] != s_ver + 1 or bytes(row["stream_prev_hash"]) != s_head:
            findings.append(Finding(p, "BROKEN_STREAM", f"{row['stream_id']} v{row['stream_version']}"))
        recomputed = compute_hash(bytes(row["prev_hash"]), bytes(row["stream_prev_hash"]), p, envelope_of(row))
        if recomputed != bytes(row["event_hash"]):
            findings.append(Finding(p, "CONTENT_ALTERED", "event_hash does not match content"))
        # Continue from the STORED hash so one edit is reported once, not cascaded.
        prev = bytes(row["event_hash"])
        stream_heads[row["stream_id"]] = (row["stream_version"], prev)
        seen[p] = prev
        expect_pos = p + 1
    last = expect_pos - 1
    for cp_pos, cp_hash in checkpoints or []:
        if cp_pos > last:
            findings.append(Finding(cp_pos, "TRUNCATED", f"witnessed position {cp_pos} but log ends at {last}"))
        elif seen.get(cp_pos) != cp_hash:
            findings.append(Finding(cp_pos, "CHECKPOINT_MISMATCH", "history differs from witnessed checkpoint"))
    return findings
