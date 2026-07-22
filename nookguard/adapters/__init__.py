"""Generation adapters. `stub` (Commit 3) exercises the CLI/state-machine
wiring end to end with a real tiny PNG. `huggingface` (Commit 5) wraps the
real Z-Image-Turbo pipeline used in production elsewhere in this project —
non-Winnie imagery only; Winnie's identity-locked face stays ChatGPT-only per
the main project's standing rule, which this adapter does not override or
decide. `mediactl generate` refuses any name outside this set."""

from __future__ import annotations

AVAILABLE_ADAPTERS = {"stub", "huggingface"}
