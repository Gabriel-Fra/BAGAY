"""DEMO ONLY: play the insider who edits the log, so verification has something to catch.

Nothing here belongs in the real system. It exists because a demo of tamper evidence is
worth nothing unless you can watch it detect an actual tamper.
"""
from __future__ import annotations

import json

from . import chain, db


def _events(conn: db.Conn) -> list[dict]:
    return conn.query("SELECT * FROM es_events ORDER BY global_position")


def run(conn: db.Conn, mode: str) -> dict:
    rows = _events(conn)
    if len(rows) < 20:
        return {"error": "seed the demo first"}

    db.set_immutability(conn, False)                     # the attacker disables the guard rails
    try:
        if mode == "edit":
            target = next(r for r in reversed(rows) if r["event_type"] == "RepairCompleted")
            payload = json.loads(target["payload"])
            old = payload.get("actual_cost")
            payload["actual_cost"] = 0
            conn.execute("UPDATE es_events SET payload = ? WHERE global_position = ?",
                         (json.dumps(payload, sort_keys=True), target["global_position"]))
            detail = (f"changed the repair cost on event #{target['global_position']} "
                      f"from {old} to 0")
        elif mode == "delete":
            target = rows[len(rows) // 2]
            conn.execute("DELETE FROM es_events WHERE global_position = ?", (target["global_position"],))
            detail = f"deleted event #{target['global_position']} ({target['event_type']})"
        elif mode == "truncate":
            cut = rows[-8]["global_position"]
            conn.execute("DELETE FROM es_events WHERE global_position >= ?", (cut,))
            conn.execute("UPDATE es_chain_head SET position = ?, head_hash = ? WHERE singleton = 1",
                         (rows[-9]["global_position"], rows[-9]["event_hash"]))
            detail = f"deleted the newest {len(rows) - (len(rows) - 8)} events, from #{cut}"
        else:                                            # rewrite: edit, then recompute every later hash
            idx = len(rows) // 2
            target = rows[idx]
            payload = json.loads(target["payload"])
            payload["note"] = "rewritten"
            target["payload"] = json.dumps(payload, sort_keys=True)
            prev = rows[idx - 1]["event_hash"] if idx else chain.ZERO
            heads: dict[str, str] = {}
            for r in rows[:idx]:
                heads[r["stream_id"]] = r["event_hash"]
            for r in rows[idx:]:
                sprev = heads.get(r["stream_id"], chain.ZERO)
                h = chain.compute_hash(prev, sprev, r["global_position"], chain.envelope_of(r))
                conn.execute("UPDATE es_events SET payload = ?, prev_hash = ?, stream_prev_hash = ?, "
                             "event_hash = ? WHERE global_position = ?",
                             (r["payload"], prev, sprev, h, r["global_position"]))
                prev, heads[r["stream_id"]] = h, h
            conn.execute("UPDATE es_chain_head SET position = ?, head_hash = ? WHERE singleton = 1",
                         (rows[-1]["global_position"], prev))
            detail = (f"edited event #{target['global_position']} and recomputed every hash after it, "
                      f"so the chain is internally consistent again")
        conn.commit()
    finally:
        db.set_immutability(conn, True)                  # and puts the guard rails back

    without = chain.verify(conn, use_witness=False)
    with_witness = chain.verify(conn, use_witness=True)
    return {
        "mode": mode,
        "what_the_attacker_did": detail,
        "without_witness": {"detected": not without["ok"],
                            "kinds": sorted({f["kind"] for f in without["findings"]})},
        "with_witness": {"detected": not with_witness["ok"],
                         "kinds": sorted({f["kind"] for f in with_witness["findings"]})},
        "report": with_witness,
    }
