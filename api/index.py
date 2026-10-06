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
    import traceback
    traceback.print_exc()

