-- BAGAY read models, personal-data vault, and access control (PostgreSQL 16)
-- Every table in schema "proj" is DISPOSABLE: it can be dropped and rebuilt by replaying es.events.

CREATE SCHEMA IF NOT EXISTS proj;
CREATE SCHEMA IF NOT EXISTS vault;
CREATE SCHEMA IF NOT EXISTS iam;

-- ---------------------------------------------------------------------------
-- Consumer bookkeeping (exactly-once EFFECT on top of at-least-once delivery)
-- A projector applies event N only if N = last_position + 1, in the same
-- transaction that advances last_position. N <= last is a duplicate (skip);
-- N > last + 1 is a gap (pull the missing range from es.events first).
-- ---------------------------------------------------------------------------
CREATE TABLE proj.consumer_offsets (
  consumer       TEXT PRIMARY KEY,
  last_position  BIGINT      NOT NULL DEFAULT 0,
  rebuilt_at     TIMESTAMPTZ,
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Current state of every asset (Registry projector)
-- ---------------------------------------------------------------------------
CREATE TABLE proj.asset_current (
  asset_id            TEXT PRIMARY KEY,                 -- 'BGY-1380600000-SL-00012'
  name                TEXT NOT NULL,
  category            TEXT NOT NULL,                    -- STREETLIGHT, DRAINAGE, BUILDING, ...
  purok               TEXT,
  lat                 DOUBLE PRECISION,
  lng                 DOUBLE PRECISION,
  property_no         TEXT,                             -- COA property number, if any
  status              TEXT NOT NULL,                    -- see lifecycle in design doc
  condition           TEXT,                             -- GOOD | FAIR | POOR | UNSAFE
  custodian_role      TEXT,
  acquired_on         DATE,
  acquisition_cost    NUMERIC(14,2),
  fund_source         TEXT,
  last_inspected_at   TIMESTAMPTZ,
  last_repaired_at    TIMESTAMPTZ,
  open_issues         INTEGER NOT NULL DEFAULT 0,
  open_work_orders    INTEGER NOT NULL DEFAULT 0,
  lifetime_repair_cost NUMERIC(14,2) NOT NULL DEFAULT 0,
  stream_version      INTEGER NOT NULL,
  stream_head_hash    BYTEA   NOT NULL,
  as_of_position      BIGINT  NOT NULL
);
CREATE INDEX asset_current_cat_idx    ON proj.asset_current (category, status);
CREATE INDEX asset_current_purok_idx  ON proj.asset_current (purok);

-- ---------------------------------------------------------------------------
-- Human-readable history (Timeline projector); public flag drives the QR page
-- ---------------------------------------------------------------------------
CREATE TABLE proj.asset_timeline (
  global_position  BIGINT PRIMARY KEY,
  asset_id         TEXT   NOT NULL,
  stream_version   INTEGER NOT NULL,
  event_type       TEXT   NOT NULL,
  occurred_at      TIMESTAMPTZ NOT NULL,
  trust_level      TEXT   NOT NULL,
  summary_en       TEXT   NOT NULL,
  summary_fil      TEXT   NOT NULL,
  is_public        BOOLEAN NOT NULL,
  event_hash       BYTEA  NOT NULL
);
CREATE INDEX asset_timeline_asset_idx ON proj.asset_timeline (asset_id, stream_version);

-- ---------------------------------------------------------------------------
-- Issue inbox (public claims awaiting triage)
-- ---------------------------------------------------------------------------
CREATE TABLE proj.issue_inbox (
  issue_id      UUID PRIMARY KEY,
  asset_id      TEXT NOT NULL,
  category      TEXT NOT NULL,
  description   TEXT,
  status        TEXT NOT NULL,          -- NEW | ACCEPTED | DUPLICATE | REJECTED | RESOLVED
  duplicate_of  UUID,
  reported_at   TIMESTAMPTZ NOT NULL,
  triaged_at    TIMESTAMPTZ,
  photo_hashes  TEXT[] NOT NULL DEFAULT '{}'
);
CREATE INDEX issue_inbox_status_idx ON proj.issue_inbox (status, reported_at);

-- ---------------------------------------------------------------------------
-- Maintenance queue (Work-order projector)
-- ---------------------------------------------------------------------------
CREATE TABLE proj.work_queue (
  work_order_id   UUID PRIMARY KEY,
  asset_id        TEXT NOT NULL,
  priority        TEXT NOT NULL,        -- P1 (safety) .. P4
  status          TEXT NOT NULL,        -- OPEN | IN_PROGRESS | DONE | CANCELLED
  assigned_role   TEXT,
  opened_at       TIMESTAMPTZ NOT NULL,
  due_on          DATE,
  started_at      TIMESTAMPTZ,
  completed_at    TIMESTAMPTZ,
  actual_cost     NUMERIC(14,2),
  source_issue_id UUID
);
CREATE INDEX work_queue_status_idx ON proj.work_queue (status, priority, due_on);

-- ---------------------------------------------------------------------------
-- Hazard impact (feeds SDG 11.5.3-style counts)
-- ---------------------------------------------------------------------------
CREATE TABLE proj.hazard_events (
  hazard_id    TEXT PRIMARY KEY,         -- 'hazard:2026-TC-KRISTINE' style id
  name         TEXT NOT NULL,
  hazard_type  TEXT NOT NULL,            -- TYPHOON | FLOOD | EARTHQUAKE | FIRE | OTHER
  started_on   DATE NOT NULL,
  ended_on     DATE
);

CREATE TABLE proj.hazard_damage (
  global_position     BIGINT PRIMARY KEY,
  hazard_id           TEXT,
  asset_id            TEXT NOT NULL,
  category            TEXT NOT NULL,
  severity            TEXT NOT NULL,     -- MINOR | MAJOR | DESTROYED
  service_disrupted   BOOLEAN NOT NULL,
  damaged_at          TIMESTAMPTZ NOT NULL,
  restored_at         TIMESTAMPTZ,
  estimated_cost      NUMERIC(14,2)
);
CREATE INDEX hazard_damage_hazard_idx ON proj.hazard_damage (hazard_id, category);

-- ---------------------------------------------------------------------------
-- Reliability analytics (Python/pandas analytics consumer, refreshed in batches)
-- ---------------------------------------------------------------------------
CREATE TABLE proj.asset_reliability (
  asset_id          TEXT PRIMARY KEY,
  failures          INTEGER NOT NULL,
  mtbf_days         NUMERIC(10,1),
  mttr_days         NUMERIC(10,1),
  repair_cost_12m   NUMERIC(14,2),
  risk_score        NUMERIC(5,2),        -- transparent weighted score, documented in design doc
  computed_at       TIMESTAMPTZ NOT NULL,
  as_of_position    BIGINT NOT NULL
);

-- ---------------------------------------------------------------------------
-- Personal-data vault (crypto-shredding). Events carry only subject_ref.
-- Deleting a subject's key row makes every ciphertext for that subject unreadable,
-- satisfying erasure requests without editing the immutable log.
-- ---------------------------------------------------------------------------
CREATE TABLE vault.subject_keys (
  subject_ref   UUID PRIMARY KEY,
  wrapped_key   BYTEA NOT NULL,          -- data key encrypted with the master key (KMS / env secret)
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE vault.subject_data (
  subject_ref   UUID NOT NULL,
  field         TEXT NOT NULL,           -- 'contact_mobile', 'full_name', ...
  ciphertext    BYTEA NOT NULL,          -- AES-256-GCM(data_key, value)
  PRIMARY KEY (subject_ref, field)
);

CREATE TABLE vault.shred_log (
  subject_ref   UUID PRIMARY KEY,
  shredded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  request_ref   TEXT NOT NULL            -- data-subject request reference (RA 10173)
);

-- ---------------------------------------------------------------------------
-- Users and roles
-- ---------------------------------------------------------------------------
CREATE TYPE iam.role AS ENUM (
  'PUNONG_BARANGAY',   -- approves high-impact events, seals turnover checkpoints
  'SECRETARY',         -- registers assets, triages reports
  'TREASURER',         -- records costs and fund sources
  'KAGAWAD',           -- committee oversight, read + inspections
  'FIELD_WORKER',      -- inspections, damage and repair records (offline PWA)
  'VERIFIER',          -- incoming officials, BIT members, C/MLGOO, COA: read + verify + export
  'ADMIN'              -- user management only; cannot write domain events
);

CREATE TABLE iam.users (
  user_id        UUID PRIMARY KEY,
  display_name   TEXT NOT NULL,
  email          TEXT UNIQUE,
  role           iam.role NOT NULL,
  password_hash  TEXT,                    -- argon2id
  active         BOOLEAN NOT NULL DEFAULT TRUE,
  term_label     TEXT,                    -- e.g. '2026-2030'
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

GRANT USAGE ON SCHEMA proj TO bagay_reader, bagay_writer;
GRANT SELECT ON ALL TABLES IN SCHEMA proj TO bagay_reader;
