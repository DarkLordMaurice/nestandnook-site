"""Commit 25 observe/judge driver -- thin CLI wrapper so the orchestrating
Cowork agent can do a real prepare/submit round with minimal round trips.
This module NEVER fabricates a review result -- "prepare" returns exactly
what nookguard.cli's observe-prepare/judge-prepare returns (the real
system prompt, image path, containment id, review-pack hash), and
"submit" reads a response file the orchestrating agent wrote from an
actual Task/Agent subagent call, hashes it itself (matching exactly what
cli.py's server-side re-verification expects), and calls observe-submit/
judge-submit for real.

Usage:
  python -m nookguard.commit25_driver prepare-observe <run_id> <candidate_sha256> <role>
  python -m nookguard.commit25_driver submit-observe <run_id> <candidate_sha256> <role> <containment_id> <review_pack_sha256> <response_file> <reviewer_session_id>
  python -m nookguard.commit25_driver prepare-judge <run_id> <candidate_sha256>
  python -m nookguard.commit25_driver submit-judge <run_id> <candidate_sha256> <containment_id> <review_pack_sha256> <response_file> <reviewer_session_id>
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

SITE_ROOT = Path(__file__).resolve().parent.parent
STORE_ROOT = SITE_ROOT / "nookguard_store_real_regression"


def run_cli(args: list[str]) -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "nookguard.cli", *args],
        cwd=str(SITE_ROOT), capture_output=True, text=True,
    )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": "non-JSON output", "stdout": proc.stdout, "stderr": proc.stderr,
                "returncode": proc.returncode}


def main():
    verb = sys.argv[1]
    rest = sys.argv[2:]
    if verb == "prepare-observe":
        run_id, cand, role = rest[:3]
        result = run_cli(["observe-prepare", "--store-root", str(STORE_ROOT), "--run-id", run_id,
                           "--candidate-sha256", cand, "--role", role])
    elif verb == "submit-observe":
        run_id, cand, role, containment_id, review_pack_sha256, response_file, reviewer_session_id = rest[:7]
        raw_hash = hashlib.sha256(Path(response_file).read_text(encoding="utf-8").encode("utf-8")).hexdigest()
        result = run_cli(["observe-submit", "--store-root", str(STORE_ROOT), "--run-id", run_id,
                           "--candidate-sha256", cand, "--role", role, "--response-file", response_file,
                           "--containment-id", containment_id, "--reviewer-session-id", reviewer_session_id,
                           "--raw-response-sha256", raw_hash, "--review-pack-sha256", review_pack_sha256])
    elif verb == "prepare-judge":
        run_id, cand = rest[:2]
        result = run_cli(["judge-prepare", "--store-root", str(STORE_ROOT), "--run-id", run_id,
                           "--candidate-sha256", cand])
    elif verb == "submit-judge":
        run_id, cand, containment_id, review_pack_sha256, response_file, reviewer_session_id = rest[:6]
        raw_hash = hashlib.sha256(Path(response_file).read_text(encoding="utf-8").encode("utf-8")).hexdigest()
        result = run_cli(["judge-submit", "--store-root", str(STORE_ROOT), "--run-id", run_id,
                           "--candidate-sha256", cand, "--response-file", response_file,
                           "--containment-id", containment_id, "--reviewer-session-id", reviewer_session_id,
                           "--raw-response-sha256", raw_hash, "--review-pack-sha256", review_pack_sha256])
    else:
        result = {"ok": False, "error": f"unknown verb {verb}"}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
