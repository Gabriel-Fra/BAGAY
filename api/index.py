"""Vercel Serverless Function entrypoint for BAGAY.
Imports the FastAPI app and ensures database tables are initialized.
"""
from __future__ import annotations

import os
import sys

# Ensure root directory is in sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Default to /tmp when running on Vercel without external DB/media
if "BAGAY_DB" not in os.environ and os.environ.get("VERCEL"):
    os.environ["BAGAY_DB"] = "sqlite:////tmp/bagay_demo.db"

if "BAGAY_MEDIA_DIR" not in os.environ and os.environ.get("VERCEL"):
    os.environ["BAGAY_MEDIA_DIR"] = "/tmp/media"

from backend import chain, db, seed
from backend.api import app

# Automatically ensure DB tables exist and seed demo data on cold start
try:
    conn = db.connect()
    try:
        head = chain.head(conn)
        if head["position"] == 0:
            seed.build(conn)
    except Exception:
        db.init_db(reset=False)
        db.set_immutability(conn, True)
        head = chain.head(conn)
        if head["position"] == 0:
            seed.build(conn)
    finally:
        conn.close()
except Exception as exc:
    print(f"[BAGAY Init] Startup DB notice: {exc}", file=sys.stderr)
