"""Password auth and server-side sessions.

Deliberately boring and dependency-free (stdlib hashlib/hmac/secrets only), matching the
project's "dependency-light" rule. Login material lives in iam_users/iam_sessions, never
in es_events: an event's actor_id is just the opaque user_id this module hands out.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import secrets

from . import db

ITERATIONS = 260_000
SESSION_TTL_HOURS = 12
COOKIE_NAME = "bagay_session"

OFFICIAL_ROLES = {"SECRETARY", "FIELD_WORKER", "TREASURER", "KAGAWAD", "PUNONG_BARANGAY",
                  "ADMIN", "VERIFIER"}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt),
                               ITERATIONS).hex()


def create_user(conn: db.Conn, *, username: str, password: str, display_name: str, role: str,
                purok: str | None = None, term_label: str | None = None) -> dict:
    username = username.strip().lower()
    if conn.one("SELECT user_id FROM iam_users WHERE username = ?", (username,)):
        raise ValueError("that username is already taken")
    salt = secrets.token_hex(16)
    user_id = f"user:{secrets.token_hex(8)}"
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
    session_id = secrets.token_urlsafe(32)
    now = _now()
    expires = now + dt.timedelta(hours=SESSION_TTL_HOURS)
    conn.execute("INSERT INTO iam_sessions (session_id, user_id, created_at, expires_at) "
                "VALUES (?, ?, ?, ?)", (session_id, user_id, now.isoformat(), expires.isoformat()))
    conn.commit()
    return session_id


def end_session(conn: db.Conn, session_id: str) -> None:
    conn.execute("DELETE FROM iam_sessions WHERE session_id = ?", (session_id,))
    conn.commit()


def current_user(conn: db.Conn, session_id: str | None) -> dict | None:
    if not session_id:
        return None
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


def public_user(row: dict) -> dict:
    return {"userId": row["user_id"], "username": row["username"], "displayName": row["display_name"],
            "role": row["role"], "purok": row.get("purok")}
