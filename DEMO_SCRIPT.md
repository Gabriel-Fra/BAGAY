# Demo script (five minutes)

Before you start: `python run.py --reset` then `python run.py`, open http://localhost:8000,
and leave the Integrity tab for last.

**0:00 Frame the problem (30 s).**
"A barangay owns streetlights, canals, footbridges. When leadership changes, and the
secretary and treasurer change with it, the maintenance history tends to leave with them.
The next turnover is the November 2026 barangay elections."

**0:30 Dashboard (30 s).**
110 assets, 30 needing attention, 1,333 events. "Nothing here is stored as a status field.
Every number is derived by replaying the log."

**1:00 One asset (90 s).** Assets, open the first one.
Walk down the history: a resident report, an officer inspection, a work order, the repair and
its cost. Point at the trust badges: "a resident's scan is a claim; an officer's inspection is
attested; disposal needs approval." Then "State as of a past point": type an earlier position
and rebuild. "This is the question an incoming administration actually asks: what condition
was this in before the turnover?"

**2:30 Work queue (45 s).** Accept a resident report. "The claim becomes an officer's decision,
and a work order opens. The resident's report is still in the log, unchanged."

**3:15 Insights (30 s).** Point at the hazard card: assets damaged, service disrupted, not yet
restored. "This is the shape SDG indicator 11.5.3 asks for, and it falls out of ordinary work."

**3:45 Integrity, the finish (75 s).**
1. "Verify the whole log." Green: 1,333 events, 7 witness checkpoints match.
2. "Edit a repair cost." The chain catches it on its own.
3. "Edit and recompute every later hash." The chain alone **misses** it. The witnessed
   checkpoint catches it. Say the line: "that is why checkpoints leave the barangay: to the
   C/MLGOO, the Full Disclosure board, a public mirror."
4. "Drop and replay": every read model deleted and rebuilt identically from the log.
5. "Download turnover pack" if there is time: events, checkpoints, and a verifier, so the
   incoming administration does not have to trust anyone.

**5:00 Close.** "The demo runs on SQLite in one process. The design, the schema and the API for
the PostgreSQL, RabbitMQ and Java version are in the repo, and the next steps are in TODO.md."

## If something breaks live

- Refresh; the UI is stateless.
- `python run.py --reset` reseeds in about two seconds.
- If verification reports findings, you probably tampered and did not reset. Press "Reset demo
  data" on the Integrity tab.
