"""FastAPI application: command endpoints, query endpoints, verification, demo controls.

Command endpoints write events; query endpoints read projections. The split mirrors the
Java Command API + Python Query API in the design docs. In the demo both live in one
process so that `python run.py` is the only thing anyone has to type.
"""
from __future__ import annotations

import io
import json
import pathlib
import zipfile

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import catalog, chain, commands, db, projector

WEB = pathlib.Path(__file__).resolve().parent.parent / "web"
app = FastAPI(title="BAGAY demo", version="0.1.0")


def conn() -> db.Conn:
    return db.shared()


def _pump():
    """Run the consumers. In production a relay publishes to RabbitMQ and the consumers
    run as their own processes; here we pump them after each write and on each read."""
    projector.run_once(conn())


# =============================================================== queries
@app.get("/api/overview")
def overview():
    c = conn()
    _pump()
    counts = c.one("SELECT COUNT(*) AS assets, "
                   "SUM(CASE WHEN status = 'NEEDS_ATTENTION' THEN 1 ELSE 0 END) AS needs, "
                   "SUM(CASE WHEN status = 'UNDER_REPAIR' THEN 1 ELSE 0 END) AS repairing, "
                   "SUM(lifetime_repair_cost) AS repair_cost FROM proj_asset_current") or {}
    issues = c.one("SELECT COUNT(*) AS c FROM proj_issue_inbox WHERE status = 'NEW'") or {"c": 0}
    p1 = c.one("SELECT COUNT(*) AS c FROM proj_work_queue WHERE status != 'DONE' AND priority = 'P1'") \
        or {"c": 0}
    head = chain.head(c)
    cp = c.one("SELECT position, head_hash, created_at, reason FROM es_checkpoints "
               "ORDER BY position DESC LIMIT 1")
    return {"assets": counts.get("assets") or 0, "needs_attention": counts.get("needs") or 0,
            "under_repair": counts.get("repairing") or 0,
            "repair_cost": round(counts.get("repair_cost") or 0, 2),
            "new_reports": issues["c"], "p1_open": p1["c"],
            "log": {"events": head["position"], "head_hash": head["head_hash"]},
            "latest_checkpoint": cp,
            "witnesses": len(chain.witness_checkpoints(c))}


@app.get("/api/assets")
def list_assets(q: str = "", status: str = "", category: str = "", limit: int = 100):
    _pump()
    sql = "SELECT * FROM proj_asset_current WHERE 1 = 1"
    params: list = []
    if q:
        sql += " AND (LOWER(name) LIKE ? OR LOWER(asset_id) LIKE ? OR LOWER(purok) LIKE ?)"
        params += [f"%{q.lower()}%"] * 3
    if status:
        sql += " AND status = ?"
        params.append(status)
    if category:
        sql += " AND category = ?"
        params.append(category)
    sql += (" ORDER BY CASE status WHEN 'NEEDS_ATTENTION' THEN 0 WHEN 'UNDER_REPAIR' THEN 1 ELSE 2 END, "
            "asset_id LIMIT ?")
    params.append(limit)
    return {"assets": conn().query(sql, params)}


@app.get("/api/assets/{asset_id}")
def asset_detail(asset_id: str, as_of: int | None = Query(None, description="global position")):
    c = conn()
    _pump()
    card = c.one("SELECT * FROM proj_asset_current WHERE asset_id = ?", (asset_id,))
    if not card:
        raise HTTPException(404, "unknown asset")
    timeline = c.query("SELECT * FROM proj_asset_timeline WHERE asset_id = ? ORDER BY stream_version DESC",
                       (asset_id,))
    result = {"asset": card, "timeline": timeline}
    if as_of:
        state = commands.load_asset(c, asset_id, as_of_position=as_of)
        result["as_of"] = {"position": as_of, "state": state,
                           "timeline": [t for t in timeline if t["global_position"] <= as_of]}
    return result


@app.get("/public/assets/{asset_id}")
def public_asset(asset_id: str):
    """What a resident sees after scanning the QR tag: no login, no internal notes."""
    c = conn()
    _pump()
    card = c.one("SELECT asset_id, name, category, purok, status, condition, last_inspected_at, "
                 "last_repaired_at, stream_head_hash FROM proj_asset_current WHERE asset_id = ?",
                 (asset_id,))
    if not card:
        raise HTTPException(404, "unknown asset")
    timeline = c.query("SELECT occurred_at, event_type, trust_level, summary_en, summary_fil "
                       "FROM proj_asset_timeline WHERE asset_id = ? AND is_public = 1 "
                       "ORDER BY stream_version DESC LIMIT 20", (asset_id,))
    cp = c.one("SELECT position, head_hash, created_at FROM es_checkpoints ORDER BY position DESC LIMIT 1")
    return {"asset": card, "timeline": timeline, "latest_checkpoint": cp}


@app.get("/api/queue")
def queues():
    c = conn()
    _pump()
    return {
        "issues": c.query("SELECT i.*, a.name FROM proj_issue_inbox i "
                          "LEFT JOIN proj_asset_current a ON a.asset_id = i.asset_id "
                          "WHERE i.status = 'NEW' ORDER BY i.reported_at DESC LIMIT 50"),
        "work_orders": c.query("SELECT w.*, a.name FROM proj_work_queue w "
                               "LEFT JOIN proj_asset_current a ON a.asset_id = w.asset_id "
                               "WHERE w.status != 'DONE' "
                               "ORDER BY w.priority, w.opened_at LIMIT 50"),
    }


@app.get("/api/insights")
def insights():
    c = conn()
    _pump()
    by_category = c.query(
        "SELECT category, COUNT(*) AS assets, "
        "SUM(CASE WHEN status IN ('NEEDS_ATTENTION','UNDER_REPAIR') THEN 1 ELSE 0 END) AS needs, "
        "SUM(lifetime_repair_cost) AS cost, SUM(failure_episodes) AS episodes "
        "FROM proj_asset_current GROUP BY category ORDER BY cost DESC")
    worst = c.query("SELECT asset_id, name, purok, failure_episodes, lifetime_repair_cost, status "
                    "FROM proj_asset_current ORDER BY lifetime_repair_cost DESC LIMIT 8")
    hazards = []
    for h in c.query("SELECT * FROM proj_hazard_events ORDER BY started_on DESC"):
        agg = c.one("SELECT COUNT(*) AS damaged, "
                    "SUM(service_disrupted) AS disrupted, "
                    "SUM(CASE WHEN restored_at IS NULL THEN 1 ELSE 0 END) AS unrestored, "
                    "SUM(estimated_cost) AS cost FROM proj_hazard_damage WHERE hazard_id = ?",
                    (h["hazard_id"],)) or {}
        per_cat = c.query("SELECT category, COUNT(*) AS n FROM proj_hazard_damage "
                          "WHERE hazard_id = ? GROUP BY category ORDER BY n DESC", (h["hazard_id"],))
        hazards.append({**h, **{k: (v or 0) for k, v in agg.items()}, "by_category": per_cat})
    return {"by_category": by_category, "worst": worst, "hazards": hazards}


# =============================================================== commands
@app.post("/api/commands/{event_type}")
def command(event_type: str, body: dict = Body(...)):
    c = conn()
    try:
        row = commands.submit(
            c, asset_id=body.get("assetId"), stream_id=body.get("streamId"),
            event_type=event_type, payload=body.get("payload", {}),
            actor_role=body.get("actorRole", "SECRETARY"),
            expected_version=body.get("expectedVersion"),
            command_id=body.get("commandId"), occurred_at=body.get("occurredAt"),
            source=body.get("source", "WEB"))
    except commands.Denied as exc:
        raise HTTPException(403, str(exc)) from exc
    except chain.Conflict as exc:
        return JSONResponse(status_code=409, content={"error": "conflict", "streamId": exc.stream_id,
                                                      "currentVersion": exc.current_version})
    _pump()
    return {"eventId": row["event_id"], "globalPosition": row["global_position"],
            "streamVersion": row["stream_version"], "eventHash": row["event_hash"],
            "duplicate": row.get("duplicate", False)}


@app.post("/public/assets/{asset_id}/reports")
def public_report(asset_id: str, body: dict = Body(...)):
    c = conn()
    row = commands.report_issue(c, asset_id=asset_id,
                                issue_category=body.get("issueCategory", "OTHER"),
                                description=body.get("description", ""),
                                command_id=body.get("commandId"))
    _pump()
    return {"eventId": row["event_id"], "globalPosition": row["global_position"]}


# =============================================================== integrity
@app.post("/api/verify")
def verify(use_witness: bool = True):
    return chain.verify(conn(), use_witness=use_witness)


@app.get("/api/checkpoints")
def checkpoints():
    c = conn()
    return {"checkpoints": c.query("SELECT * FROM es_checkpoints ORDER BY position DESC LIMIT 20"),
            "witness": chain.witness_checkpoints(c)}


@app.post("/api/checkpoints")
def make_checkpoint(reason: str = "MANUAL"):
    return chain.create_checkpoint(conn(), reason=reason)


@app.post("/api/turnover/seal")
def seal(body: dict = Body(default={})):
    row = commands.seal_turnover(
        conn(), psgc=body.get("psgc", "0000000000"),
        outgoing_term=body.get("outgoingTerm", "2023-2026"),
        incoming_term=body.get("incomingTerm", "2026-2030"),
        witnesses=body.get("witnesses", ["BIT_CSO_REP", "CMLGOO"]))
    _pump()
    return {"globalPosition": row["global_position"], "eventHash": row["event_hash"]}


@app.get("/api/exports/turnover-pack")
def turnover_pack():
    """Everything an incoming administration needs, and nothing it has to trust."""
    c = conn()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        events = c.query("SELECT * FROM es_events ORDER BY global_position")
        z.writestr("events.jsonl", "\n".join(json.dumps(e, default=str) for e in events))
        z.writestr("checkpoints.json", json.dumps(chain.witness_checkpoints(c), indent=2))
        z.writestr("assets.json", json.dumps(c.query("SELECT * FROM proj_asset_current"), indent=2,
                                             default=str))
        verifier = pathlib.Path(__file__).with_name("chain.py").read_text()
        z.writestr("verifier/chain.py", verifier)
        z.writestr("README.txt",
                   "BAGAY turnover pack\n\n"
                   "events.jsonl      every event, in order, with its hashes\n"
                   "checkpoints.json  checkpoints held by witnesses outside the barangay\n"
                   "assets.json       the asset registry rebuilt from those events\n"
                   "verifier/         recompute the chain yourself; you do not have to trust us\n")
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": "attachment; filename=turnover-pack.zip"})


# =============================================================== demo controls
@app.post("/api/demo/tamper")
def tamper(mode: str = Query("edit", pattern="^(edit|delete|truncate|rewrite)$")):
    """DEMO ONLY. Plays the insider who can switch the database guard rails off.

    This endpoint does not exist in the real system. It is here so the demo can show what
    the hash chain and the witnessed checkpoints catch.
    """
    from . import demo_tamper
    return demo_tamper.run(conn(), mode)


@app.post("/api/demo/reset")
def reset_demo():
    """Wipe and re-seed, so a demo can be run again from a clean state."""
    from . import seed
    c = conn()
    db.wipe(c)
    seed.build(c)
    return {"ok": True, "events": chain.head(c)["position"]}


@app.post("/api/admin/rebuild")
def rebuild():
    """Delete every read model and replay the log. Proves the projections are disposable."""
    c = conn()
    before = c.one("SELECT COUNT(*) AS c FROM proj_asset_current")["c"]
    applied = projector.rebuild_all(c)
    after = c.one("SELECT COUNT(*) AS c FROM proj_asset_current")["c"]
    return {"events_replayed": applied, "assets_before": before, "assets_after": after,
            "identical": before == after}


@app.get("/api/log")
def log_tail(limit: int = 30, after: int = 0):
    rows = chain.read_events(conn(), after=after, limit=limit)
    rows.reverse()
    return {"events": [{k: r[k] for k in ("global_position", "stream_id", "stream_version",
                                          "event_type", "trust_level", "actor_role",
                                          "occurred_at", "event_hash")} for r in rows]}


# =============================================================== static web app
@app.get("/", response_class=HTMLResponse)
def index():
    return (WEB / "index.html").read_text()


@app.get("/a/{asset_id}", response_class=HTMLResponse)
def qr_landing(asset_id: str):
    return (WEB / "index.html").read_text().replace("__BOOT__", f'{{"view":"public","asset":"{asset_id}"}}')


@app.get("/favicon.ico")
def favicon():
    path = WEB / "favicon.ico"
    return FileResponse(path) if path.exists() else JSONResponse({}, status_code=404)


app.mount("/static", StaticFiles(directory=str(WEB)), name="static")
