"""FastAPI application: command endpoints, query endpoints, verification, demo controls.

Command endpoints write events; query endpoints read projections. The split mirrors the
Java Command API + Python Query API in the design docs. In the demo both live in one
process so that `python run.py` is the only thing anyone has to type.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import pathlib
import queue
import re
import zipfile

from fastapi import Body, Cookie, Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import auth, catalog, chain, commands, db, projector

WEB = pathlib.Path(__file__).resolve().parent.parent / "web"
MEDIA = pathlib.Path(__file__).resolve().parent.parent / "media"
MEDIA.mkdir(exist_ok=True)
app = FastAPI(title="BAGAY demo", version="0.1.0")


def conn() -> db.Conn:
    return db.shared()


def _pump():
    """Run the consumers. In production a relay publishes to RabbitMQ and the consumers
    run as their own processes; here we pump them after each write and on each read."""
    projector.run_once(conn())


# =============================================================== auth
def get_current_user(session: str | None = Cookie(None, alias=auth.COOKIE_NAME)) -> dict | None:
    return auth.current_user(conn(), session)


def require_user(user: dict | None = Depends(get_current_user)) -> dict:
    if not user:
        raise HTTPException(401, "log in first")
    return user


def require_official(user: dict = Depends(require_user)) -> dict:
    if user["role"] not in auth.OFFICIAL_ROLES:
        raise HTTPException(403, "an official account is needed for this")
    return user


def _set_session_cookie(resp: JSONResponse, session_id: str) -> JSONResponse:
    resp.set_cookie(auth.COOKIE_NAME, session_id, httponly=True, samesite="lax",
                    max_age=auth.SESSION_TTL_HOURS * 3600)
    return resp


@app.post("/api/auth/register")
def register(body: dict = Body(...)):
    """Residents only: self-serve sign-up so anyone can file a report without an official
    creating their account first. Officials are provisioned by the demo seed instead."""
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    display_name = (body.get("displayName") or username).strip()
    purok = body.get("purok")
    if len(username) < 3:
        raise HTTPException(400, "username needs at least 3 characters")
    if len(password) < 8:
        raise HTTPException(400, "password needs at least 8 characters")
    try:
        user = auth.create_user(conn(), username=username, password=password,
                                display_name=display_name, role="PUBLIC", purok=purok)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    session_id = auth.start_session(conn(), user["user_id"])
    return _set_session_cookie(
        JSONResponse({"user": {"userId": user["user_id"], "username": user["username"],
                               "displayName": user["display_name"], "role": user["role"],
                               "purok": user["purok"]}}), session_id)


@app.post("/api/auth/login")
def login(body: dict = Body(...)):
    row = auth.verify_password(conn(), username=body.get("username", ""),
                               password=body.get("password", ""))
    if not row:
        raise HTTPException(401, "wrong username or password")
    session_id = auth.start_session(conn(), row["user_id"])
    return _set_session_cookie(JSONResponse({"user": auth.public_user(row)}), session_id)


@app.post("/api/auth/logout")
def logout(session: str | None = Cookie(None, alias=auth.COOKIE_NAME)):
    if session:
        auth.end_session(conn(), session)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE_NAME)
    return resp


@app.get("/api/auth/me")
def me(user: dict | None = Depends(get_current_user)):
    return {"user": auth.public_user(user) if user else None}


# =============================================================== live feed (phone -> PC)
_subscribers: set[queue.SimpleQueue] = set()


def _broadcast(payload: dict) -> None:
    for q in list(_subscribers):
        q.put(payload)


@app.get("/api/stream")
async def stream(user: dict = Depends(require_user)):
    """Server-Sent Events: whatever a resident's phone submits shows up here within a
    couple seconds on every open dashboard, no polling, no extra dependency."""
    q: queue.SimpleQueue = queue.SimpleQueue()
    _subscribers.add(q)

    async def gen():
        try:
            yield "retry: 3000\nevent: ready\ndata: {}\n\n"
            while True:
                try:
                    payload = await asyncio.to_thread(q.get, True, 20)
                    yield f"data: {json.dumps(payload)}\n\n"
                except queue.Empty:
                    yield ": keep-alive\n\n"
        finally:
            _subscribers.discard(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# =============================================================== photos
@app.post("/api/photos")
def upload_photo(body: dict = Body(...), user: dict = Depends(require_user)):
    """Client re-encodes the capture through a <canvas> before it ever gets here, which
    strips EXIF (GPS, device id) for free — no server-side image library required."""
    data_url = body.get("dataUrl", "")
    if not data_url.startswith("data:image/"):
        raise HTTPException(400, "expected a data: image URL")
    header, _, b64 = data_url.partition(",")
    content_type = header[5:].split(";")[0]
    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}.get(content_type, "jpg")
    try:
        raw = base64.b64decode(b64)
    except Exception as exc:                                    # noqa: BLE001
        raise HTTPException(400, "could not decode photo") from exc
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(413, "photo is too large (8 MB max)")
    digest = hashlib.sha256(raw).hexdigest()
    sub = MEDIA / digest[:2]
    sub.mkdir(exist_ok=True)
    path = sub / f"{digest}.{ext}"
    if not path.exists():
        path.write_bytes(raw)
    return {"hash": digest, "contentType": content_type, "url": f"/media/{digest[:2]}/{digest}.{ext}"}


@app.post("/api/qr/decode")
def decode_qr(body: dict = Body(...)):
    """Decode a QR code image submitted as a data URL (camera frame or file upload).
    Returns the decoded text and extracted asset ID without requiring user login."""
    data_url = body.get("dataUrl", "")
    if not data_url.startswith("data:image/"):
        raise HTTPException(400, "expected a data: image URL")
    _, _, b64 = data_url.partition(",")
    try:
        raw = base64.b64decode(b64)
    except Exception as exc:
        raise HTTPException(400, "could not decode image data") from exc

    text = ""
    try:
        import cv2
        import numpy as np
        arr = np.frombuffer(raw, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is not None:
            detectors = []
            if hasattr(cv2, "QRCodeDetectorAruco"):
                detectors.append(cv2.QRCodeDetectorAruco())
            detectors.append(cv2.QRCodeDetector())

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
            passes = [img, gray]
            try:
                thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                               cv2.THRESH_BINARY, 51, 0)
                passes.append(thresh)
                passes.append(cv2.bitwise_not(gray))
            except Exception:
                pass

            for det in detectors:
                for p in passes:
                    try:
                        val, _, _ = det.detectAndDecode(p)
                        if val and val.strip():
                            text = val.strip()
                            break
                    except Exception:
                        pass
                if text:
                    break

            if not text:
                try:
                    resized = cv2.resize(gray, (0, 0), fx=1.5, fy=1.5, interpolation=cv2.INTER_LINEAR)
                    for det in detectors:
                        val, _, _ = det.detectAndDecode(resized)
                        if val and val.strip():
                            text = val.strip()
                            break
                except Exception:
                    pass
    except Exception:
        pass

    asset_id = None
    if text:
        m = re.search(r"(BGY-[A-Za-z0-9-]+)", text, re.IGNORECASE)
        if m:
            asset_id = m.group(1).upper()
        else:
            asset_id = text.strip().upper()

    return {"found": bool(asset_id), "text": text, "asset_id": asset_id}


# =============================================================== queries
@app.get("/api/overview")
def overview(user: dict = Depends(require_official)):
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
def list_assets(q: str = "", status: str = "", category: str = "", limit: int = 100,
                user: dict = Depends(require_official)):
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
def asset_detail(asset_id: str, as_of: int | None = Query(None, description="global position"),
                 user: dict = Depends(require_official)):
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


@app.get("/public/sample-asset")
def sample_asset(user: dict = Depends(require_user)):
    """A NEEDS_ATTENTION asset id to try the resident flow with when there is no QR tag
    in hand yet (e.g. scan /a/{asset_id} directly once tags are printed)."""
    c = conn()
    _pump()
    row = (c.one("SELECT asset_id FROM proj_asset_current WHERE status = 'NEEDS_ATTENTION' "
                "ORDER BY RANDOM() LIMIT 1")
           or c.one("SELECT asset_id FROM proj_asset_current ORDER BY RANDOM() LIMIT 1"))
    return {"assetId": (row or {}).get("asset_id")}


@app.get("/public/assets/{asset_id}")
def public_asset(asset_id: str, user: dict = Depends(require_user)):
    """What a resident sees after scanning the QR tag and signing in: no internal notes."""
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


@app.get("/api/my/reports")
def my_reports(user: dict = Depends(require_user)):
    """A resident's own reports and their status. Nobody else's."""
    c = conn()
    _pump()
    rows = c.query("SELECT i.*, a.name AS asset_name FROM proj_issue_inbox i "
                   "LEFT JOIN proj_asset_current a ON a.asset_id = i.asset_id "
                   "WHERE i.reported_by = ? ORDER BY i.reported_at DESC LIMIT 100",
                   (user["user_id"],))
    return {"reports": rows}


@app.get("/api/queue")
def queues(user: dict = Depends(require_official)):
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
def insights(user: dict = Depends(require_official)):
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
def command(event_type: str, body: dict = Body(...), user: dict = Depends(require_official)):
    c = conn()
    try:
        row = commands.submit(
            c, asset_id=body.get("assetId"), stream_id=body.get("streamId"),
            event_type=event_type, payload=body.get("payload", {}),
            actor_role=user["role"], actor_id=user["user_id"],
            expected_version=body.get("expectedVersion"),
            command_id=body.get("commandId"), occurred_at=body.get("occurredAt"),
            source=body.get("source", "WEB"), attachments=body.get("attachments"))
    except commands.Denied as exc:
        raise HTTPException(403, str(exc)) from exc
    except chain.Conflict as exc:
        return JSONResponse(status_code=409, content={"error": "conflict", "streamId": exc.stream_id,
                                                      "currentVersion": exc.current_version})
    _pump()
    if not row.get("duplicate"):
        _broadcast({"kind": "event", "eventType": event_type, "assetId": body.get("assetId"),
                   "globalPosition": row["global_position"], "actorRole": user["role"],
                   "actorName": user["display_name"]})
    return {"eventId": row["event_id"], "globalPosition": row["global_position"],
            "streamVersion": row["stream_version"], "eventHash": row["event_hash"],
            "duplicate": row.get("duplicate", False)}


@app.post("/public/assets/{asset_id}/reports")
def public_report(asset_id: str, body: dict = Body(...), user: dict = Depends(require_user)):
    if user["role"] != "PUBLIC":
        raise HTTPException(403, "official accounts record findings through the dashboard instead")
    c = conn()
    row = commands.report_issue(c, asset_id=asset_id,
                                issue_category=body.get("issueCategory", "OTHER"),
                                description=body.get("description", ""),
                                command_id=body.get("commandId"), actor_id=user["user_id"],
                                attachments=body.get("attachments"))
    _pump()
    if not row.get("duplicate"):
        _broadcast({"kind": "report", "eventType": "IssueReported", "assetId": asset_id,
                   "globalPosition": row["global_position"], "actorName": user["display_name"],
                   "purok": user.get("purok")})
    return {"eventId": row["event_id"], "globalPosition": row["global_position"]}


# =============================================================== integrity
@app.post("/api/verify")
def verify(use_witness: bool = True, user: dict = Depends(require_official)):
    return chain.verify(conn(), use_witness=use_witness)


@app.get("/api/checkpoints")
def checkpoints(user: dict = Depends(require_official)):
    c = conn()
    return {"checkpoints": c.query("SELECT * FROM es_checkpoints ORDER BY position DESC LIMIT 20"),
            "witness": chain.witness_checkpoints(c)}


@app.post("/api/checkpoints")
def make_checkpoint(reason: str = "MANUAL", user: dict = Depends(require_official)):
    return chain.create_checkpoint(conn(), reason=reason)


@app.post("/api/turnover/seal")
def seal(body: dict = Body(default={}), user: dict = Depends(require_official)):
    row = commands.seal_turnover(
        conn(), psgc=body.get("psgc", "0000000000"),
        outgoing_term=body.get("outgoingTerm", "2023-2026"),
        incoming_term=body.get("incomingTerm", "2026-2030"),
        witnesses=body.get("witnesses", ["BIT_CSO_REP", "CMLGOO"]))
    _pump()
    return {"globalPosition": row["global_position"], "eventHash": row["event_hash"]}


@app.get("/api/exports/turnover-pack")
def turnover_pack(user: dict = Depends(require_official)):
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
def tamper(mode: str = Query("edit", pattern="^(edit|delete|truncate|rewrite)$"),
           user: dict = Depends(require_official)):
    """DEMO ONLY. Plays the insider who can switch the database guard rails off.

    This endpoint does not exist in the real system. It is here so the demo can show what
    the hash chain and the witnessed checkpoints catch.
    """
    from . import demo_tamper
    return demo_tamper.run(conn(), mode)


@app.post("/api/demo/reset")
def reset_demo(user: dict = Depends(require_official)):
    """Wipe and re-seed, so a demo can be run again from a clean state."""
    from . import seed
    c = conn()
    db.wipe(c)
    seed.build(c)
    return {"ok": True, "events": chain.head(c)["position"]}


@app.post("/api/admin/rebuild")
def rebuild(user: dict = Depends(require_official)):
    """Delete every read model and replay the log. Proves the projections are disposable."""
    c = conn()
    before = c.one("SELECT COUNT(*) AS c FROM proj_asset_current")["c"]
    applied = projector.rebuild_all(c)
    after = c.one("SELECT COUNT(*) AS c FROM proj_asset_current")["c"]
    return {"events_replayed": applied, "assets_before": before, "assets_after": after,
            "identical": before == after}


@app.get("/api/log")
def log_tail(limit: int = 30, after: int = 0, user: dict = Depends(require_official)):
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


app.mount("/media", StaticFiles(directory=str(MEDIA)), name="media")
app.mount("/static", StaticFiles(directory=str(WEB)), name="static")
