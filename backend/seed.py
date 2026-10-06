"""Seed Barangay Halimbawa with clean baseline data for demonstrations.

Creates all 110 registered municipal assets, sets up historical maintenance records,
and provisions exactly 5 active demo tickets (2 new resident reports, 2 open work orders,
and 1 in-progress repair) with sample photos attached.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import random

from . import auth, chain, commands, db, projector

DEMO_ACCOUNTS = [
    ("kapitana", "Barangay2026!", "Kap. Rosa Villanueva", "PUNONG_BARANGAY", None),
    ("secretary", "Barangay2026!", "Ana Dela Cruz", "SECRETARY", None),
    ("fieldworker", "Barangay2026!", "Mico Santos", "FIELD_WORKER", None),
    ("resident", "Barangay2026!", "Julma Reyes", "PUBLIC", "Purok 3"),
]

PSGC = "1380600000"                       # illustrative code, Barangay Halimbawa
BARANGAY = "Barangay Halimbawa"
PUROKS = ["Purok 1", "Purok 2", "Purok 3", "Purok 4", "Purok 5"]

PLAN = [                                  # (category, count, label, unit cost)
    ("SL", 46, "Streetlight", 18_500), ("DR", 22, "Drainage line", 92_000),
    ("RD", 8, "Concrete pathway", 480_000), ("FB", 3, "Footbridge", 310_000),
    ("CC", 2, "Covered court", 1_850_000), ("HS", 1, "Health station", 2_400_000),
    ("DC", 2, "Day care centre", 1_250_000), ("EC", 1, "Evacuation centre", 3_100_000),
    ("WS", 4, "Water point", 145_000), ("CT", 9, "CCTV camera", 26_000),
    ("GN", 3, "Generator set", 210_000), ("VH", 2, "Patrol tricycle", 165_000),
    ("RE", 6, "Rescue equipment set", 48_000), ("BH", 1, "Barangay hall", 4_200_000),
]

HAZARDS = [
    ("2025-HABAGAT", "Habagat Flooding 2025", "FLOOD", dt.date(2025, 8, 3), dt.date(2025, 8, 9)),
    ("2026-TC-ESTER", "Typhoon Ester 2026", "TYPHOON", dt.date(2026, 7, 19), dt.date(2026, 7, 24)),
]

SAMPLE_SVGS = {
    "streetlight": """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 600 400' width='600' height='400'>
  <rect width='600' height='400' fill='#1E293B'/>
  <rect x='285' y='60' width='30' height='340' fill='#475569'/>
  <path d='M300 60 Q300 20 380 20 L420 20' stroke='#475569' stroke-width='16' fill='none'/>
  <circle cx='420' cy='30' r='24' fill='#334155'/>
  <line x1='410' y1='25' x2='430' y2='35' stroke='#EF4444' stroke-width='4'/>
  <polygon points='400,60 440,60 420,100' fill='rgba(239,68,68,0.2)'/>
  <text x='300' y='360' font-family='sans-serif' font-weight='700' font-size='20' fill='#F8FAFC' text-anchor='middle'>DAMAGED STREETLIGHT FIXTURE</text>
  <text x='300' y='385' font-family='sans-serif' font-size='14' fill='#94A3B8' text-anchor='middle'>Asset ID: BGY-1380600000-SL-00001 · Purok 1</text>
</svg>""",
    "drainage": """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 600 400' width='600' height='400'>
  <rect width='600' height='400' fill='#334155'/>
  <rect x='100' y='80' width='400' height='260' fill='#1E293B' rx='8'/>
  <path d='M100 240 Q300 280 500 240 L500 340 L100 340 Z' fill='#0284C7' opacity='0.7'/>
  <rect x='220' y='210' width='70' height='35' fill='#78350F' rx='4' transform='rotate(12 250 220)'/>
  <rect x='310' y='230' width='80' height='40' fill='#92400E' rx='4' transform='rotate(-8 350 240)'/>
  <text x='300' y='50' font-family='sans-serif' font-weight='700' font-size='20' fill='#F8FAFC' text-anchor='middle'>BLOCKED DRAINAGE CANAL</text>
  <text x='300' y='380' font-family='sans-serif' font-size='14' fill='#94A3B8' text-anchor='middle'>Asset ID: BGY-1380600000-DR-00047 · Purok 3</text>
</svg>""",
    "footbridge": """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 600 400' width='600' height='400'>
  <rect width='600' height='400' fill='#0F172A'/>
  <rect x='50' y='220' width='500' height='30' fill='#64748B'/>
  <rect x='50' y='160' width='500' height='12' fill='#94A3B8'/>
  <line x1='120' y1='160' x2='120' y2='220' stroke='#94A3B8' stroke-width='8'/>
  <line x1='240' y1='160' x2='240' y2='220' stroke='#94A3B8' stroke-width='8'/>
  <line x1='360' y1='160' x2='340' y2='220' stroke='#EF4444' stroke-width='8'/>
  <line x1='480' y1='160' x2='480' y2='220' stroke='#94A3B8' stroke-width='8'/>
  <rect x='260' y='220' width='60' height='10' fill='#EF4444'/>
  <text x='300' y='100' font-family='sans-serif' font-weight='700' font-size='20' fill='#F8FAFC' text-anchor='middle'>BROKEN FOOTBRIDGE WALKWAY &amp; RAILING</text>
  <text x='300' y='360' font-family='sans-serif' font-size='14' fill='#94A3B8' text-anchor='middle'>Asset ID: BGY-1380600000-FB-00077 · Purok 2</text>
</svg>"""
}


def _ensure_sample_photos() -> dict[str, dict]:
    import os
    from . import db
    _media_env = os.environ.get("BAGAY_MEDIA_DIR")
    if not _media_env and db.is_serverless():
        _media_env = "/tmp/media"
    media_dir = pathlib.Path(_media_env) if _media_env else (pathlib.Path(__file__).resolve().parent.parent / "media")
    try:
        media_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    res = {}
    for key, svg_text in SAMPLE_SVGS.items():
        raw = svg_text.encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        sub = media_dir / digest[:2]
        try:
            sub.mkdir(parents=True, exist_ok=True)
            path = sub / f"{digest}.svg"
            if not path.exists():
                path.write_bytes(raw)
        except Exception:
            pass
        res[key] = {"hash": digest, "url": f"/media/{digest[:2]}/{digest}.svg", "contentType": "image/svg+xml"}
    return res


def _d(date: dt.date, hour: int = 9) -> dt.datetime:
    return dt.datetime(date.year, date.month, date.day, hour, tzinfo=dt.timezone.utc)


def build(conn: db.Conn, *, assets_per_category=1.0, seed: int = 20260915) -> dict:
    rng = random.Random(seed)
    photos = _ensure_sample_photos()

    # 1. Initialize Registry
    chain.append(conn, stream_id=f"barangay:{PSGC}", event_type="RegistryInitialized",
                 payload={"psgc": PSGC, "barangay_name": BARANGAY, "municipality": "Sample City",
                          "province": "Metro Manila", "term_label": "2023-2026"},
                 actor_role="SYSTEM", occurred_at=_d(dt.date(2023, 12, 1)))

    # 2. Register all 110 assets and assign custody
    assets: list[dict] = []
    serial = 0
    for cat, count, label, unit in PLAN:
        target_count = max(1, int(count * assets_per_category))
        for _ in range(target_count):
            serial += 1
            purok = PUROKS[(serial - 1) % len(PUROKS)]
            acquired = dt.date(rng.randint(2014, 2024), rng.randint(1, 12), rng.randint(1, 28))
            asset_id = f"BGY-{PSGC}-{cat}-{serial:05d}"
            commands.register_asset(
                conn, asset_id=asset_id, name=f"{label}, {purok}", category=cat, purok=purok,
                acquired_on=acquired.isoformat(),
                acquisition_cost=round(unit * rng.uniform(0.9, 1.1), 2),
                fund_source=rng.choice(["BARANGAY_DEVELOPMENT_FUND", "GENERAL_FUND", "LGU_AID"]),
                backfilled=True, occurred_at=_d(dt.date(2023, 12, 2)))
            commands.submit(conn, asset_id=asset_id, event_type="CustodyAssigned",
                            actor_role="SECRETARY", occurred_at=_d(dt.date(2023, 12, 2)),
                            payload={"custodian_role": "SECRETARY", "document_ref": f"PAR-{serial:04d}"})
            assets.append({"id": asset_id, "cat": cat, "purok": purok, "unit": unit})

    # 3. Declare Natural Hazards (for SDG 11.5.3 Disaster Metrics)
    for hid, name, kind, start, end in HAZARDS:
        commands.declare_hazard(conn, hazard_id=hid, name=name, hazard_type=kind,
                                started_on=start.isoformat(), ended_on=end.isoformat(),
                                occurred_at=_d(start))

    def _asset_at(idx: int) -> str:
        return assets[idx % len(assets)]["id"]

    # 4. Historical Maintenance & Damage (Completed in past)
    # A few completed repairs so charts/financial totals have realistic values
    past_repair_1 = _asset_at(4)
    commands.record_damage(conn, asset_id=past_repair_1, severity="MINOR", service_disrupted=False,
                           hazard_id="hazard:2025-HABAGAT", estimated_cost=4200,
                           occurred_at=_d(dt.date(2025, 8, 5)), actor_role="KAGAWAD")
    wo1 = commands.open_work_order(conn, asset_id=past_repair_1, priority="P3",
                                   due_on="2025-08-20", occurred_at=_d(dt.date(2025, 8, 6)))
    wo1_id = json.loads(wo1["payload"])["work_order_id"]
    commands.start_repair(conn, asset_id=past_repair_1, work_order_id=wo1_id, occurred_at=_d(dt.date(2025, 8, 7)))
    commands.complete_repair(conn, asset_id=past_repair_1, work_order_id=wo1_id,
                             actual_cost=3800, resulting_condition="GOOD", occurred_at=_d(dt.date(2025, 8, 10)))

    past_repair_2 = _asset_at(68)
    commands.record_inspection(conn, asset_id=past_repair_2, condition="POOR",
                               findings="Surface cracks sealed", occurred_at=_d(dt.date(2025, 11, 12)))
    wo2 = commands.open_work_order(conn, asset_id=past_repair_2, priority="P2",
                                   due_on="2025-11-30", occurred_at=_d(dt.date(2025, 11, 13)))
    wo2_id = json.loads(wo2["payload"])["work_order_id"]
    commands.start_repair(conn, asset_id=past_repair_2, work_order_id=wo2_id, occurred_at=_d(dt.date(2025, 11, 14)))
    commands.complete_repair(conn, asset_id=past_repair_2, work_order_id=wo2_id,
                             actual_cost=48500, resulting_condition="GOOD", occurred_at=_d(dt.date(2025, 11, 20)))

    past_repair_3 = _asset_at(94)
    commands.record_damage(conn, asset_id=past_repair_3, severity="MAJOR", service_disrupted=True,
                           hazard_id="hazard:2026-TC-ESTER", estimated_cost=15000,
                           occurred_at=_d(dt.date(2026, 7, 21)), actor_role="KAGAWAD")
    wo3 = commands.open_work_order(conn, asset_id=past_repair_3, priority="P1",
                                   due_on="2026-07-28", occurred_at=_d(dt.date(2026, 7, 22)))
    wo3_id = json.loads(wo3["payload"])["work_order_id"]
    commands.start_repair(conn, asset_id=past_repair_3, work_order_id=wo3_id, occurred_at=_d(dt.date(2026, 7, 23)))
    commands.complete_repair(conn, asset_id=past_repair_3, work_order_id=wo3_id,
                             actual_cost=14200, resulting_condition="GOOD", occurred_at=_d(dt.date(2026, 7, 27)))

    # Midpoint witness checkpoint
    chain.create_checkpoint(conn, reason="SCHEDULED")

    # 5. EXACTLY 5 ACTIVE ASSET TICKETS FOR DEMONSTRATION
    # -------------------------------------------------------------
    # Ticket 1: Resident Report (NEW - Awaiting Triage by Secretary)
    # Asset: Streetlight BGY-1380600000-SL-00001
    commands.report_issue(
        conn, asset_id=_asset_at(0), issue_category="NOT_WORKING",
        description="Streetlight lamp broken and dangling after stormy winds. Street is pitch black at night.",
        actor_id="user:resident", occurred_at=_d(dt.date(2026, 9, 26), 19),
        attachments=[photos["streetlight"]])

    # Ticket 2: Resident Report (NEW - Awaiting Triage by Secretary)
    # Asset: Drainage BGY-1380600000-DR-00047
    commands.report_issue(
        conn, asset_id=_asset_at(46), issue_category="CLOGGED",
        description="Drainage canal blocked with trash and silt. Flooding path towards Purok 3 daycare center.",
        actor_id="user:resident", occurred_at=_d(dt.date(2026, 9, 27), 8),
        attachments=[photos["drainage"]])

    # Ticket 3: Open Work Order (P1 SAFETY - Awaiting Field Worker to "Start repair")
    # Asset: Footbridge BGY-1380600000-FB-00076
    ev_fb = commands.report_issue(
        conn, asset_id=_asset_at(76), issue_category="UNSAFE",
        description="Cracked wooden footbridge planks and broken handrail over creek. Severe child hazard.",
        actor_id="user:resident", occurred_at=_d(dt.date(2026, 9, 25), 14),
        attachments=[photos["footbridge"]])
    issue_fb_id = json.loads(ev_fb["payload"])["issue_id"]
    commands.triage_issue(conn, asset_id=_asset_at(76), issue_id=issue_fb_id, decision="ACCEPTED",
                          occurred_at=_d(dt.date(2026, 9, 26), 9))
    commands.open_work_order(conn, asset_id=_asset_at(76), priority="P1", due_on="2026-10-02",
                             source_issue_id=issue_fb_id, occurred_at=_d(dt.date(2026, 9, 26), 10))

    # Ticket 4: Open Work Order (P2 URGENT - Awaiting Field Worker to "Start repair")
    # Asset: Water point BGY-1380600000-WS-00086
    commands.record_inspection(conn, asset_id=_asset_at(86), condition="POOR",
                               findings="Main pump cylinder gasket leaking continuously. Water pressure depleted.",
                               occurred_at=_d(dt.date(2026, 9, 27), 11))
    commands.open_work_order(conn, asset_id=_asset_at(86), priority="P2", due_on="2026-10-05",
                             occurred_at=_d(dt.date(2026, 9, 27), 14))

    # Ticket 5: Work Order (IN_PROGRESS - Awaiting Field Worker to click "Complete")
    # Asset: Covered Court BGY-1380600000-CC-00078
    commands.record_damage(conn, asset_id=_asset_at(78), severity="MINOR", service_disrupted=False,
                           hazard_id="hazard:2026-TC-ESTER", estimated_cost=8500,
                           occurred_at=_d(dt.date(2026, 9, 24), 10), actor_role="KAGAWAD")
    wo5 = commands.open_work_order(conn, asset_id=_asset_at(78), priority="P3", due_on="2026-10-10",
                                   occurred_at=_d(dt.date(2026, 9, 25), 9))
    wo5_id = json.loads(wo5["payload"])["work_order_id"]
    commands.start_repair(conn, asset_id=_asset_at(78), work_order_id=wo5_id,
                          occurred_at=_d(dt.date(2026, 9, 28), 8))

    # 6. Final witness checkpoint
    chain.create_checkpoint(conn, reason="SCHEDULED")

    # 7. Rebuild all projections cleanly
    projector.rebuild_all(conn)

    # 8. Provision Demo Users
    for username, password, display_name, role, purok in DEMO_ACCOUNTS:
        try:
            auth.create_user(conn, username=username, password=password,
                             display_name=display_name, role=role, purok=purok)
        except ValueError:
            pass

    # 9. Generate sample QR codes containing only raw asset IDs
    try:
        import segno
        qdir = pathlib.Path(__file__).resolve().parent.parent / "web" / "qr"
        qdir.mkdir(exist_ok=True)
        sl_asset = next((a["id"] for a in assets if a["cat"] == "SL"), _asset_at(0))
        dr_asset = next((a["id"] for a in assets if a["cat"] == "DR"), _asset_at(1))
        fb_asset = next((a["id"] for a in assets if a["cat"] == "FB"), _asset_at(2))
        samples = [
            (sl_asset, "qr_streetlight"),
            (dr_asset, "qr_drainage"),
            (fb_asset, "qr_footbridge")
        ]
        for aid, fname in samples:
            qr = segno.make(aid, error="h")
            qr.save(qdir / f"{fname}.png", scale=8, border=2)
            qr.save(qdir / f"{fname}.svg", scale=8, border=2)
    except Exception:
        pass

    head = chain.head(conn)
    return {"events": head["position"], "head_hash": head["head_hash"], "assets": len(assets),
            "accounts": [{"username": u, "password": p, "role": r}
                         for u, p, _, r, _ in DEMO_ACCOUNTS]}


if __name__ == "__main__":
    db.init_db(reset=True)
    c = db.connect()
    print(build(c))
