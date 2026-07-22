-- NookGuard Commit 16: owner_queue table.
--
-- Appendix E ("Owner Decision Packet") and Appendix J's operational
-- runbook ("Maurice can see and resolve only the owner queue from the
-- private dashboard") both describe this concept, but neither is SQL --
-- unlike Commit 14's three tables, there is no existing sketch to
-- transcribe. This migration is a new design, built to match two real,
-- already-existing sources rather than invented from scratch:
--
-- 1. nookguard/owner_queue.py (Python, wired into cmd_judge since before
--    this commit) already persists a JSON-file-backed queue entry with
--    fields: asset_id, candidate_sha256, reasons, risk_tier, result_state,
--    status, queued_at, resolved_at, resolved_by, decision. Every one of
--    those fields is reproduced below under the same name, so the two
--    representations describe the same thing and a future cutover (the
--    Python side calling this Worker instead of writing its own JSON file
--    -- still not done, see README "Unresolved risks") doesn't have to
--    rename anything.
-- 2. Appendix E's own table (page 48) adds what owner_queue.py does not
--    yet have: `question` (its own required field, "one exact decision,
--    not a broad status request"), `requirement_id` (part of its
--    "Asset/requirement" row), `evidence_json` (its "Evidence" row:
--    "candidate, reference, highlighted crops, literal observations, page
--    preview"), and `consequences_json` (its "Consequences" row: "what
--    changes on site and whether override is permanent/temporary" --
--    filled in at resolution time, not at enqueue time, since the actual
--    consequence of a decision isn't known until the decision is made).
--
-- Appendix E's "Options" row ("approve exact hash, reject, revise-spec,
-- regenerate, or defer") is NOT a schema constraint here -- SQLite has no
-- portable enum type, and D1 doesn't support CHECK-constraint-with-list
-- reliably across all client libraries. It's enforced in application code
-- instead: see src/enforce.mjs's isValidOwnerDecisionOption() and
-- tests/enforce.test.mjs for the five-value allow-list this maps to, the
-- same "enforce in Worker transaction, not in schema" pattern Appendix H
-- already established for reviews.
--
-- Appendix E's "No persuasion" row ("do not include generator's defense or
-- Claude's preferred creative interpretation") is a content-quality rule,
-- not a mechanically checkable one -- there is no reliable code-level test
-- for "is this text persuasive." It is NOT enforced here, and is not
-- pretended to be; see README "Unresolved risks."

CREATE TABLE owner_queue (
  entry_id TEXT PRIMARY KEY,
  asset_id TEXT NOT NULL,
  candidate_sha256 TEXT NOT NULL,
  requirement_id TEXT,
  question TEXT NOT NULL,
  reasons_json TEXT NOT NULL,
  risk_tier TEXT NOT NULL,
  result_state TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  status TEXT NOT NULL,
  decision TEXT,
  consequences_json TEXT,
  queued_at TEXT NOT NULL,
  resolved_at TEXT,
  resolved_by TEXT,
  FOREIGN KEY(candidate_sha256) REFERENCES generation_attempts(candidate_sha256)
);

CREATE INDEX idx_owner_queue_status ON owner_queue(status);
CREATE INDEX idx_owner_queue_candidate_sha256 ON owner_queue(candidate_sha256);
