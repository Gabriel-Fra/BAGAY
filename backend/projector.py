"""Consumers: build read models from the log, idempotently.

Each projector remembers the last global position it applied and advances that offset in
the same transaction as the read-model write. Re-delivering an event changes nothing, and
a gap is filled by reading the log directly, so the broker is a delivery channel and never
the source of truth. Dropping a projection and replaying from position 1 rebuilds it.
"""
from __future__ import annotations

import json

from . import catalog, chain, db

CONSUMERS = ("registry", "workflow", "hazard")


def _offset(conn: db.Conn, name: str) -> int:
    row = conn.one("SELECT last_position FROM proj_consumer_offsets WHERE consumer = ?", (name,))
    if row is None:
        conn.execute("INSERT INTO proj_consumer_offsets (consumer, last_position, updated_at) "
                     "VALUES (?, 0, ?)", (name, chain.now_iso()))
        return 0
    return row["last_position"]


def _advance(conn: db.Conn, name: str, position: int) -> None:
    conn.execute("UPDATE proj_consumer_offsets SET last_position = ?, updated_at = ? WHERE consumer = ?",
                 (position, chain.now_iso(), name))


# --------------------------------------------------------------------------- registry + timeline
def _apply_registry(conn: db.Conn, e: dict) -> None:
    if not e["stream_id"].startswith("asset:"):
        return
    asset_id = e["stream_id"].split(":", 1)[1]
    events = chain.stream_events(conn, e["stream_id"], as_of_position=e["global_position"])
    s = catalog.rebuild(events)
    row = (asset_id, s["name"], s["category"], s["purok"], s["status"], s["condition"],
           s["custodian_role"], s["acquired_on"], s["acquisition_cost"], s["fund_source"],
           s["last_inspected_at"], s["last_repaired_at"], s["open_issues"], s["open_work_orders"],
           s["lifetime_repair_cost"], s["failure_episodes"], s["version"], s["head_hash"],
           e["global_position"])
    cols = ("asset_id, name, category, purok, status, condition, custodian_role, acquired_on, "
            "acquisition_cost, fund_source, last_inspected_at, last_repaired_at, open_issues, "
            "open_work_orders, lifetime_repair_cost, failure_episodes, stream_version, "
            "stream_head_hash, as_of_position")
    marks = ", ".join("?" * len(row))
    if db.IS_PG:
        updates = ", ".join(f"{c.strip()} = EXCLUDED.{c.strip()}" for c in cols.split(",")[1:])
        conn.execute(f"INSERT INTO proj_asset_current ({cols}) VALUES ({marks}) "
                     f"ON CONFLICT (asset_id) DO UPDATE SET {updates}", row)
    else:
        conn.execute(f"INSERT OR REPLACE INTO proj_asset_current ({cols}) VALUES ({marks})", row)

    en, fil = catalog.summarize(e)
    _, public = catalog.EVENTS[e["event_type"]]
    tl = (e["global_position"], asset_id, e["stream_version"], e["event_type"], e["occurred_at"],
          e["recorded_at"], e["trust_level"], e["actor_role"], en, fil, 1 if public else 0,
          e["event_hash"], e["payload"])
    verb = "INSERT OR REPLACE INTO" if not db.IS_PG else "INSERT INTO"
    tail = "" if not db.IS_PG else " ON CONFLICT (global_position) DO NOTHING"
    conn.execute(f"{verb} proj_asset_timeline (global_position, asset_id, stream_version, event_type, "
                 f"occurred_at, recorded_at, trust_level, actor_role, summary_en, summary_fil, "
                 f"is_public, event_hash, payload) VALUES ({', '.join('?' * len(tl))}){tail}", tl)


# --------------------------------------------------------------------------- issues + work orders
def _apply_workflow(conn: db.Conn, e: dict) -> None:
    p = catalog.payload_of(e)
    t = e["event_type"]
    asset_id = e["stream_id"].split(":", 1)[1] if e["stream_id"].startswith("asset:") else None
    if t == "IssueReported":
        verb = "INSERT OR REPLACE INTO" if not db.IS_PG else "INSERT INTO"
        conn.execute(f"{verb} proj_issue_inbox (issue_id, asset_id, category, description, status, "
                     f"reported_at) VALUES (?, ?, ?, ?, 'NEW', ?)",
                     (p["issue_id"], asset_id, p.get("issue_category", "OTHER"),
                      p.get("description", ""), e["occurred_at"]))
    elif t == "IssueTriaged":
        conn.execute("UPDATE proj_issue_inbox SET status = ?, duplicate_of = ?, triaged_at = ? "
                     "WHERE issue_id = ?",
                     (p.get("decision"), p.get("duplicate_of"), e["occurred_at"], p["issue_id"]))
    elif t == "WorkOrderOpened":
        verb = "INSERT OR REPLACE INTO" if not db.IS_PG else "INSERT INTO"
        conn.execute(f"{verb} proj_work_queue (work_order_id, asset_id, priority, status, opened_at, "
                     f"due_on) VALUES (?, ?, ?, 'OPEN', ?, ?)",
                     (p["work_order_id"], asset_id, p.get("priority", "P3"), e["occurred_at"],
                      p.get("due_on")))
    elif t == "RepairStarted":
        conn.execute("UPDATE proj_work_queue SET status = 'IN_PROGRESS', started_at = ? "
                     "WHERE work_order_id = ?", (e["occurred_at"], p["work_order_id"]))
    elif t == "RepairCompleted":
        conn.execute("UPDATE proj_work_queue SET status = 'DONE', completed_at = ?, actual_cost = ? "
                     "WHERE work_order_id = ?",
                     (e["occurred_at"], p.get("actual_cost", 0), p["work_order_id"]))


# --------------------------------------------------------------------------- hazard impact
def _apply_hazard(conn: db.Conn, e: dict) -> None:
    p = catalog.payload_of(e)
    t = e["event_type"]
    if t == "HazardDeclared":
        verb = "INSERT OR REPLACE INTO" if not db.IS_PG else "INSERT INTO"
        conn.execute(f"{verb} proj_hazard_events (hazard_id, name, hazard_type, started_on, ended_on) "
                     f"VALUES (?, ?, ?, ?, ?)",
                     (p["hazard_id"], p["name"], p["hazard_type"], p["started_on"], p.get("ended_on")))
    elif t == "DamageRecorded":
        asset_id = e["stream_id"].split(":", 1)[1]
        cat = conn.one("SELECT category FROM proj_asset_current WHERE asset_id = ?", (asset_id,))
        verb = "INSERT OR REPLACE INTO" if not db.IS_PG else "INSERT INTO"
        conn.execute(f"{verb} proj_hazard_damage (global_position, hazard_id, asset_id, category, "
                     f"severity, service_disrupted, damaged_at, estimated_cost) "
                     f"VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                     (e["global_position"], p.get("hazard_id"), asset_id,
                      (cat or {}).get("category", "OT"), p.get("severity", "MINOR"),
                      1 if p.get("service_disrupted") else 0, e["occurred_at"],
                      p.get("estimated_cost", 0)))
    elif t == "RepairCompleted":
        asset_id = e["stream_id"].split(":", 1)[1]
        conn.execute("UPDATE proj_hazard_damage SET restored_at = ? "
                     "WHERE asset_id = ? AND restored_at IS NULL", (e["occurred_at"], asset_id))


APPLIERS = {"registry": _apply_registry, "workflow": _apply_workflow, "hazard": _apply_hazard}
TYPES = {
    "registry": None,                                   # everything on asset streams
    "workflow": ["IssueReported", "IssueTriaged", "WorkOrderOpened", "RepairStarted", "RepairCompleted"],
    "hazard": ["HazardDeclared", "DamageRecorded", "RepairCompleted"],
}


def run_once(conn: db.Conn, batch: int = 2000) -> int:
    """Apply every event each consumer has not seen yet. Returns events applied."""
    applied = 0
    for name in CONSUMERS:
        offset = _offset(conn, name)
        events = chain.read_events(conn, after=offset, limit=batch, types=TYPES[name])
        last = offset
        for e in events:
            APPLIERS[name](conn, e)
            last = e["global_position"]
            applied += 1
        head = chain.head(conn)["position"]
        # caught up: move to the head so filtered-out event types never look like gaps
        _advance(conn, name, last if len(events) == batch else head)
        conn.commit()
    return applied


def rebuild_all(conn: db.Conn) -> int:
    """Drop every read model and replay the log. This is the cheap superpower of the design."""
    for table in ("proj_asset_current", "proj_asset_timeline", "proj_issue_inbox",
                  "proj_work_queue", "proj_hazard_events", "proj_hazard_damage"):
        conn.execute(f"DELETE FROM {table}")
    conn.execute("UPDATE proj_consumer_offsets SET last_position = 0")
    conn.commit()
    return run_once(conn, batch=1_000_000)
