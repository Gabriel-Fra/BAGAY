#!/usr/bin/env python3
"""Start the BAGAY demo.

    python run.py            # seed on first run, then serve on http://localhost:8000
    python run.py --reset    # wipe and re-seed
    python run.py --seed-only
"""
from __future__ import annotations

import argparse
import sys

from backend import chain, db, projector, seed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="delete the database and seed again")
    ap.add_argument("--seed-only", action="store_true")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    db.init_db(reset=args.reset)
    conn = db.connect()
    db.set_immutability(conn, True)
    head = chain.head(conn)
    if head["position"] == 0:
        print("Seeding Barangay Halimbawa ...", flush=True)
        info = seed.build(conn)
        print(f"  {info['events']} events, {info['assets']} assets, head {info['head_hash'][:16]}")
    else:
        projector.run_once(conn)
        print(f"Log has {head['position']} events, head {head['head_hash'][:16]}")
    conn.close()

    if args.seed_only:
        return 0

    import uvicorn
    print(f"\n  BAGAY demo on http://{args.host}:{args.port}\n")
    uvicorn.run("backend.api:app", host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
