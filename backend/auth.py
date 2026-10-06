"""Password auth and server-side sessions.

Deliberately boring and dependency-free (stdlib hashlib/hmac/secrets only), matching the
project's "dependency-light" rule. Login material lives in iam_users/iam_sessions, never
in es_events: an event's actor_id is just the opaque user_id this module hands out.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import secrets

from . import db

ITERATIONS = 260_000
SESSION_TTL_HOURS = 12
COOKIE_NAME = "bagay_session"
SECRET_KEY = os.environ.get("BAGAY_AUTH_SECRET", "bagay-invariable-signing-secret-2026")

OFFICIAL_ROLES = {"SECRETARY", "FIELD_WORKER", "TREASURER", "KAGAWAD", "PUNONG_BARANGAY",
                  "ADMIN", "VERIFIER"}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _sign_payload(data: dict) -> str:
    raw = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    b64_data = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    sig = hmac.new(SECRET_KEY.encode("utf-8"), b64_data.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{b64_data}.{sig}"


def _verify_payload(token: str) -> dict | None:
    try:
        if "." not in token:
            return None
        b64_data, sig = token.split(".", 1)
        expected_sig = hmac.new(SECRET_KEY.encode("utf-8"), b64_data.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        rem = len(b64_data) % 4
        if rem > 0:
            b64_data += "=" * (4 - rem)
        raw = base64.urlsafe_b64decode(b64_data)
        data = json.loads(raw.decode("utf-8"))
        if dt.datetime.fromisoformat(data["exp"]) < _now():
            return None
        return data
    except Exception:
        return None


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt),
                               ITERATIONS).hex()


def create_user(conn: db.Conn, *, username: str, password: str, display_name: str, role: str,
                purok: str | None = None, term_label: str | None = None,
                user_id: str | None = None) -> dict:
    username = username.strip().lower()
    if conn.one("SELECT user_id FROM iam_users WHERE username = ?", (username,)):
        raise ValueError("that username is already taken")
    salt = secrets.token_hex(16)
    user_id = user_id or f"user:{secrets.token_hex(8)}"
    conn.execute(
        "INSERT INTO iam_users (user_id, username, password_hash, password_salt, display_name, "
        "role, term_label, purok, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, username, _hash(password, salt), salt, display_name.strip(), role, term_label,
         purok, _now().isoformat()))
    conn.commit()
    return {"user_id": user_id, "username": username, "display_name": display_name.strip(),
            "role": role, "purok": purok}


def verify_password(conn: db.Conn, *, username: str, password: str) -> dict | None:
    row = conn.one("SELECT * FROM iam_users WHERE username = ?", (username.strip().lower(),))
    if not row:
        return None
    if not hmac.compare_digest(_hash(password, row["password_salt"]), row["password_hash"]):
        return None
    return row


def start_session(conn: db.Conn, user_id: str) -> str:
    now = _now()
    expires = now + dt.timedelta(hours=SESSION_TTL_HOURS)
    user_row = conn.one("SELECT user_id, username, display_name, role, purok FROM iam_users WHERE user_id = ?", (user_id,))
    payload = {
        "sub": user_id,
        "username": user_row["username"] if user_row else "",
        "displayName": user_row["display_name"] if user_row else "",
        "role": user_row["role"] if user_row else "",
        "purok": user_row.get("purok") if user_row else None,
        "exp": expires.isoformat()
    }
    signed_token = _sign_payload(payload)
    try:
        conn.execute("INSERT INTO iam_sessions (session_id, user_id, created_at, expires_at) "
                    "VALUES (?, ?, ?, ?)", (signed_token, user_id, now.isoformat(), expires.isoformat()))
        conn.commit()
    except Exception:
        pass
    return signed_token


def end_session(conn: db.Conn, session_id: str) -> None:
    try:
        conn.execute("DELETE FROM iam_sessions WHERE session_id = ?", (session_id,))
        conn.commit()
    except Exception:
        pass


def current_user(conn: db.Conn, session_id: str | None) -> dict | None:
    if not session_id:
        return None

    # 1. Stateless HMAC token verification (resilient across serverless cold starts and instances)
    data = _verify_payload(session_id)
    if data:
        user_id = data["sub"]
        try:
            row = conn.one(
                "SELECT user_id, username, display_name, role, purok FROM iam_users WHERE user_id = ?",
                (user_id,))
            if row:
                return {
                    "session_id": session_id,
                    "expires_at": data["exp"],
                    "user_id": row["user_id"],
                    "username": row["username"],
                    "display_name": row["display_name"],
                    "role": row["role"],
                    "purok": row.get("purok")
                }
            if data.get("username"):
                row = conn.one(
                    "SELECT user_id, username, display_name, role, purok FROM iam_users WHERE username = ?",
                    (data["username"].strip().lower(),))
                if row:
                    return {
                        "session_id": session_id,
                        "expires_at": data["exp"],
                        "user_id": row["user_id"],
                        "username": row["username"],
                        "display_name": row["display_name"],
                        "role": row["role"],
                        "purok": row.get("purok")
                    }
        except Exception:
            pass

        return {
            "session_id": session_id,
            "expires_at": data["exp"],
            "user_id": data["sub"],
            "username": data["username"],
            "display_name": data["displayName"],
            "role": data["role"],
            "purok": data.get("purok")
        }

    # 2. Fallback to DB session table for non-signed session tokens
    try:
        row = conn.one(
            "SELECT s.session_id, s.expires_at, u.user_id, u.username, u.display_name, u.role, "
            "u.purok FROM iam_sessions s JOIN iam_users u ON u.user_id = s.user_id "
            "WHERE s.session_id = ?", (session_id,))
        if not row:
            return None
        if dt.datetime.fromisoformat(row["expires_at"]) < _now():
            end_session(conn, session_id)
            return None
        return row
    except Exception:
        return None


def public_user(row: dict) -> dict:
    return {"userId": row["user_id"], "username": row["username"], "displayName": row["display_name"],
            "role": row["role"], "purok": row.get("purok")}
