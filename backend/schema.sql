-- BAGAY demo schema. Runs on SQLite (default) and PostgreSQL.
-- The production DDL in ../db/ uses PostgreSQL types (JSONB, BYTEA, ENUM) and
-- SECURITY DEFINER triggers; this file keeps the same shape in portable SQL.

CREATE TABLE IF NOT EXISTS es_events (
  global_position   INTEGER PRIMARY KEY,
  event_id          TEXT NOT NULL UNIQUE,
  stream_id         TEXT NOT NULL,
  stream_version    INTEGER NOT NULL,
  event_type        TEXT NOT NULL,
  schema_version    INTEGER NOT NULL DEFAULT 1,
  occurred_at       TEXT NOT NULL,
  recorded_at       TEXT NOT NULL,
  actor_id          TEXT NOT NULL,
  actor_role        TEXT NOT NULL,
  trust_level       TEXT NOT NULL,
  source            TEXT NOT NULL,
  correlation_id    TEXT,
  causation_id      TEXT,
  payload           TEXT NOT NULL,
  attachments       TEXT NOT NULL DEFAULT '[]',
  prev_hash         TEXT NOT NULL,
  stream_prev_hash  TEXT NOT NULL,
  event_hash        TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS es_events_stream ON es_events (stream_id, stream_version);
CREATE INDEX IF NOT EXISTS es_events_type   ON es_events (event_type);

CREATE TABLE IF NOT EXISTS es_chain_head (
  singleton INTEGER PRIMARY KEY,
  position  INTEGER NOT NULL,
  head_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS es_stream_heads (
  stream_id TEXT PRIMARY KEY,
  version   INTEGER NOT NULL,
  head_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS es_checkpoints (
  checkpoint_no INTEGER PRIMARY KEY,
  position      INTEGER NOT NULL UNIQUE,
  head_hash     TEXT NOT NULL,
  created_at    TEXT NOT NULL,
  reason        TEXT NOT NULL,
  published_to  TEXT NOT NULL DEFAULT '[]'
);

-- Witness copies. In production these live outside the barangay (e-mail to the
-- C/MLGOO, printed slip, public mirror). Here they are a separate table that the
-- tamper demo never touches, standing in for "a copy the attacker cannot reach".
CREATE TABLE IF NOT EXISTS witness_checkpoints (
  position    INTEGER NOT NULL,
  channel     TEXT NOT NULL,
  head_hash   TEXT NOT NULL,
  received_at TEXT NOT NULL,
  PRIMARY KEY (position, channel)
);

CREATE TABLE IF NOT EXISTS proj_consumer_offsets (
  consumer      TEXT PRIMARY KEY,
  last_position INTEGER NOT NULL DEFAULT 0,
  updated_at    TEXT
);

CREATE TABLE IF NOT EXISTS proj_asset_current (
  asset_id             TEXT PRIMARY KEY,
  name                 TEXT NOT NULL,
  category             TEXT NOT NULL,
  purok                TEXT,
  status               TEXT NOT NULL,
  condition            TEXT,
  custodian_role       TEXT,
  acquired_on          TEXT,
  acquisition_cost     REAL DEFAULT 0,
  fund_source          TEXT,
  last_inspected_at    TEXT,
  last_repaired_at     TEXT,
  open_issues          INTEGER NOT NULL DEFAULT 0,
  open_work_orders     INTEGER NOT NULL DEFAULT 0,
  lifetime_repair_cost REAL NOT NULL DEFAULT 0,
  failure_episodes     INTEGER NOT NULL DEFAULT 0,
  stream_version       INTEGER NOT NULL DEFAULT 0,
  stream_head_hash     TEXT,
  as_of_position       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS proj_asset_timeline (
  global_position INTEGER PRIMARY KEY,
  asset_id        TEXT NOT NULL,
  stream_version  INTEGER NOT NULL,
  event_type      TEXT NOT NULL,
  occurred_at     TEXT NOT NULL,
  recorded_at     TEXT NOT NULL,
  trust_level     TEXT NOT NULL,
  actor_role      TEXT NOT NULL,
  summary_en      TEXT NOT NULL,
  summary_fil     TEXT NOT NULL,
  is_public       INTEGER NOT NULL,
  event_hash      TEXT NOT NULL,
  payload         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS proj_timeline_asset ON proj_asset_timeline (asset_id, stream_version);

CREATE TABLE IF NOT EXISTS proj_issue_inbox (
  issue_id     TEXT PRIMARY KEY,
  asset_id     TEXT NOT NULL,
  category     TEXT NOT NULL,
  description  TEXT,
  status       TEXT NOT NULL,
  duplicate_of TEXT,
  reported_at  TEXT NOT NULL,
  triaged_at   TEXT
);

CREATE TABLE IF NOT EXISTS proj_work_queue (
  work_order_id TEXT PRIMARY KEY,
  asset_id      TEXT NOT NULL,
  priority      TEXT NOT NULL,
  status        TEXT NOT NULL,
  opened_at     TEXT NOT NULL,
  due_on        TEXT,
  started_at    TEXT,
  completed_at  TEXT,
  actual_cost   REAL
);

CREATE TABLE IF NOT EXISTS proj_hazard_events (
  hazard_id   TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  hazard_type TEXT NOT NULL,
  started_on  TEXT NOT NULL,
  ended_on    TEXT
);

CREATE TABLE IF NOT EXISTS proj_hazard_damage (
  global_position   INTEGER PRIMARY KEY,
  hazard_id         TEXT,
  asset_id          TEXT NOT NULL,
  category          TEXT NOT NULL,
  severity          TEXT NOT NULL,
  service_disrupted INTEGER NOT NULL,
  damaged_at        TEXT NOT NULL,
  restored_at       TEXT,
  estimated_cost    REAL
);

CREATE TABLE IF NOT EXISTS iam_users (
  user_id      TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  role         TEXT NOT NULL,
  term_label   TEXT
);
