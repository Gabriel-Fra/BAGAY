"""Integration tests for authentication, role-gating, photos, and API workflows.

Run with: pytest -q
"""
from __future__ import annotations

import base64
import io
import os
import pathlib
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))


@pytest.fixture()
def client(monkeypatch):
    tmp_dir = pathlib.Path(tempfile.mkdtemp())
    db_file = tmp_dir / "test_api.db"
    media_dir = tmp_dir / "media"
    media_dir.mkdir(exist_ok=True)

    monkeypatch.setenv("BAGAY_DB", f"sqlite:///{db_file}")

    for mod in [m for m in list(sys.modules) if m.startswith("backend")]:
        del sys.modules[mod]

    from backend import api, chain, db, seed

    db.DB_URL = f"sqlite:///{db_file}"
    db.IS_PG = False
    db.init_db(reset=True)
    conn = db.connect()
    db.set_immutability(conn, True)

    # Seed the test barangay
    seed.build(conn, assets_per_category=0.1)
    conn.close()

    api.MEDIA = media_dir

    with TestClient(api.app) as test_client:
        yield test_client


def test_auth_registration_and_login_lifecycle(client):
    # Registration validation failures
    r = client.post("/api/auth/register", json={"username": "ab", "password": "password123"})
    assert r.status_code == 400
    assert "username needs at least 3 characters" in r.json()["detail"]

    r = client.post("/api/auth/register", json={"username": "resident_juan", "password": "123"})
    assert r.status_code == 400
    assert "password needs at least 8 characters" in r.json()["detail"]

    # Successful resident registration
    reg_payload = {
        "username": "resident_juan",
        "password": "Password123!",
        "displayName": "Juan Dela Cruz",
        "purok": "Purok 1",
    }
    r = client.post("/api/auth/register", json=reg_payload)
    assert r.status_code == 200
    user_data = r.json()["user"]
    assert user_data["username"] == "resident_juan"
    assert user_data["role"] == "PUBLIC"
    assert "bagay_session" in client.cookies

    # Duplicate registration conflict
    r_dup = client.post("/api/auth/register", json=reg_payload)
    assert r_dup.status_code == 409

    # Check /api/auth/me while logged in
    r_me = client.get("/api/auth/me")
    assert r_me.status_code == 200
    assert r_me.json()["user"]["username"] == "resident_juan"

    # Logout
    r_logout = client.post("/api/auth/logout")
    assert r_logout.status_code == 200

    # Check /api/auth/me after logout
    r_me_out = client.get("/api/auth/me")
    assert r_me_out.status_code == 200
    assert r_me_out.json()["user"] is None

    # Failed login with wrong password
    r_bad = client.post("/api/auth/login", json={"username": "resident_juan", "password": "wrongpassword"})
    assert r_bad.status_code == 401

    # Successful login with seeded official
    r_sec = client.post("/api/auth/login", json={"username": "secretary", "password": "Barangay2026!"})
    assert r_sec.status_code == 200
    assert r_sec.json()["user"]["role"] == "SECRETARY"


def test_role_gating_and_authorization(client):
    # 1. Unauthenticated requests to official query endpoints return 401
    assert client.get("/api/overview").status_code == 401
    assert client.get("/api/assets").status_code == 401
    assert client.get("/api/queue").status_code == 401

    # 2. Login as resident (role: PUBLIC)
    r_login = client.post("/api/auth/login", json={"username": "resident", "password": "Barangay2026!"})
    assert r_login.status_code == 200

    # Resident accessing official dashboard endpoints returns 403 Forbidden
    assert client.get("/api/overview").status_code == 403
    assert client.get("/api/assets").status_code == 403
    assert client.get("/api/queue").status_code == 403

    # Resident CAN access resident endpoints
    r_sample = client.get("/public/sample-asset")
    assert r_sample.status_code == 200
    sample_id = r_sample.json()["assetId"]
    assert sample_id is not None

    r_pub_asset = client.get(f"/public/assets/{sample_id}")
    assert r_pub_asset.status_code == 200
    assert r_pub_asset.json()["asset"]["asset_id"] == sample_id

    # 3. Login as official (role: SECRETARY)
    client.post("/api/auth/logout")
    r_sec = client.post("/api/auth/login", json={"username": "secretary", "password": "Barangay2026!"})
    assert r_sec.status_code == 200

    # Official can access official endpoints
    assert client.get("/api/overview").status_code == 200
    assert client.get("/api/assets").status_code == 200
    assert client.get("/api/queue").status_code == 200


def test_photo_upload_endpoint(client):
    # Must be logged in to upload
    assert client.post("/api/photos", json={"dataUrl": ""}).status_code == 401

    client.post("/api/auth/login", json={"username": "resident", "password": "Barangay2026!"})

    # Reject invalid data URL
    r_invalid = client.post("/api/photos", json={"dataUrl": "http://example.com/not-a-data-url"})
    assert r_invalid.status_code == 400

    # Upload valid 1x1 transparent PNG data URL
    tiny_png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    data_url = f"data:image/png;base64,{tiny_png_b64}"

    r_upload = client.post("/api/photos", json={"dataUrl": data_url})
    assert r_upload.status_code == 200
    res = r_upload.json()
    assert "hash" in res
    assert res["contentType"] == "image/png"
    assert res["url"].startswith("/media/")


def test_resident_report_submission_and_isolation(client):
    # Register Resident A
    client.post("/api/auth/register", json={
        "username": "resident_a", "password": "Password123!", "displayName": "Resident A",
    })

    # Get sample asset
    sample_id = client.get("/public/sample-asset").json()["assetId"]

    # Resident A files a report
    r_rep = client.post(f"/public/assets/{sample_id}/reports", json={
        "issueCategory": "DAMAGED",
        "description": "Cracked surface needing repair",
    })
    assert r_rep.status_code == 200
    assert "eventId" in r_rep.json()

    # Resident A checks my reports
    r_my = client.get("/api/my/reports")
    assert r_my.status_code == 200
    reports_a = r_my.json()["reports"]
    assert len(reports_a) == 1
    assert reports_a[0]["asset_id"] == sample_id
    assert reports_a[0]["description"] == "Cracked surface needing repair"

    # Register Resident B
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={
        "username": "resident_b", "password": "Password123!", "displayName": "Resident B",
    })

    # Resident B checks my reports: should be empty
    r_my_b = client.get("/api/my/reports")
    assert r_my_b.status_code == 200
    assert len(r_my_b.json()["reports"]) == 0

    # Official tries to submit public report -> 403 Forbidden
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "secretary", "password": "Barangay2026!"})
    r_forbidden = client.post(f"/public/assets/{sample_id}/reports", json={
        "issueCategory": "DAMAGED", "description": "Trying from official account",
    })
    assert r_forbidden.status_code == 403


def test_integrity_and_admin_rebuild_endpoints(client):
    # Login as secretary
    client.post("/api/auth/login", json={"username": "secretary", "password": "Barangay2026!"})

    # Chain verification
    r_ver = client.post("/api/verify")
    assert r_ver.status_code == 200
    assert r_ver.json()["ok"] is True
    assert r_ver.json()["finding_count"] == 0

    # Projection rebuild
    r_reb = client.post("/api/admin/rebuild")
    assert r_reb.status_code == 200
    assert r_reb.json()["identical"] is True


def test_qr_decode_endpoint(client):
    import segno
    qr = segno.make("BGY-1380600000-SL-00001", error="h")
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=5, border=2)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    # Test raw asset ID payload
    resp = client.post("/api/qr/decode", json={"dataUrl": f"data:image/png;base64,{b64}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["found"] is True
    assert data["asset_id"] == "BGY-1380600000-SL-00001"

    # Test URL payload extracting asset ID
    qr_url = segno.make("http://localhost:8000/a/BGY-1380600000-DR-00047", error="h")
    buf2 = io.BytesIO()
    qr_url.save(buf2, kind="png", scale=5, border=2)
    b64_url = base64.b64encode(buf2.getvalue()).decode("ascii")

    resp2 = client.post("/api/qr/decode", json={"dataUrl": f"data:image/png;base64,{b64_url}"})
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["found"] is True
    assert data2["asset_id"] == "BGY-1380600000-DR-00047"
