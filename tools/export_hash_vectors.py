"""Export event_hash test vectors for the Java Command API parity check.

Seeds a fresh, throwaway SQLite database with the real seed script, then dumps
every event's hashing inputs (prev_hash, stream_prev_hash, global_position,
envelope) and its expected event_hash, as one JSON array. That file is the
input to java-command-api's ParityCheck: if Java's Chain.computeHash
reproduces every expected_event_hash, the two implementations agree byte for
byte on the whole seeded log, which is what TODO.md's "Java Command API
parity" item asks for.

Usage:
    python -m tools.export_hash_vectors [output_path]

Requires the real `rfc8785` package (it is what backend/chain.py itself uses
to hash -- see requirements.txt). Run this with the project's normal
virtualenv, not a substitute.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import os

DB_PATH = pathlib.Path(tempfile.gettempdir()) / "bagay_hash_vectors.db"
os.environ["BAGAY_DB"] = f"sqlite:///{DB_PATH}"

from backend import chain, db, seed  # noqa: E402


def main(out_path: str = "hash_vectors.json") -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = db.connect()
    conn.raw.executescript((pathlib.Path(__file__).parent.parent / "backend" / "schema.sql").read_text())
    conn.commit()
    seed.build(conn)

    result = chain.verify(conn)
    if not result["ok"]:
        print("WARNING: the freshly seeded log does not verify cleanly:", result)

    rows = conn.query("SELECT * FROM es_events ORDER BY global_position")
    vectors = [
        {
            "global_position": row["global_position"],
            "prev_hash": row["prev_hash"],
            "stream_prev_hash": row["stream_prev_hash"],
            "expected_event_hash": row["event_hash"],
            "envelope": chain.envelope_of(row),
        }
        for row in rows
    ]
    pathlib.Path(out_path).write_text(json.dumps(vectors))
    print(f"wrote {len(vectors)} event vectors to {out_path}")
    print(f"python verify(): ok={result['ok']} events_checked={result['events_checked']}")


if __name__ == "__main__":
    main(*sys.argv[1:])
