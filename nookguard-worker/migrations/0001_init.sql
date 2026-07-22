-- NookGuard Commit 14: initial D1 schema.
--
-- The three CREATE TABLE statements below are transcribed verbatim from
-- NookGuard-Plan.docx Appendix H ("Core SQL Sketch for D1") -- every
-- column name, type, and constraint matches the sketch exactly. Nothing
-- here changes the data model the spec defines.
--
-- The three CREATE INDEX statements after each table are NOT in the
-- sketch -- the sketch is explicitly a "sketch," not a finished migration,
-- and ships no indices at all. Every query this Worker actually needs
-- (list events by run_id, look up a generation_attempt by its own primary
-- key, list reviews by candidate_sha256) is added here as a normal
-- migration-authoring judgment call, the same kind of addition Commit 2's
-- ledger.py already made on top of the schemas.py Pydantic models (see
-- BUILD-LOG Commit 2). No column, table, or constraint was added, removed,
-- or renamed.

CREATE TABLE events (
  event_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  asset_id TEXT,
  event_type TEXT NOT NULL,
  actor_role TEXT NOT NULL,
  actor_session_id TEXT,
  payload_json TEXT NOT NULL,
  payload_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX idx_events_run_id ON events(run_id);
CREATE INDEX idx_events_asset_id ON events(asset_id);

CREATE TABLE generation_attempts (
  candidate_sha256 TEXT PRIMARY KEY,
  asset_id TEXT NOT NULL,
  spec_sha256 TEXT NOT NULL,
  prompt_sha256 TEXT NOT NULL,
  generator_session_id TEXT NOT NULL,
  artifact_uri TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX idx_generation_attempts_asset_id ON generation_attempts(asset_id);

CREATE TABLE reviews (
  review_id TEXT PRIMARY KEY,
  candidate_sha256 TEXT NOT NULL,
  review_stage TEXT NOT NULL,
  reviewer_session_id TEXT NOT NULL,
  context_bundle_sha256 TEXT NOT NULL,
  result_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(candidate_sha256) REFERENCES generation_attempts(candidate_sha256)
);

CREATE INDEX idx_reviews_candidate_sha256 ON reviews(candidate_sha256);

-- Enforce in Worker transaction (Appendix H, transcribed verbatim as a
-- comment there -- SQLite/D1 has no CHECK-constraint-with-subquery or
-- cross-table trigger simple enough to express these safely, so both are
-- enforced in application code, not in the schema. See src/enforce.mjs
-- for the actual implementation and tests/enforce.test.mjs for the tests
-- proving both rules hold):
-- -- reviewer_session_id != generation_attempt.generator_session_id
-- -- approval candidate SHA must have required review stages and computed policy PASS
