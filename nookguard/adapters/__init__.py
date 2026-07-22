"""Generation adapters. Only `stub` exists as of Commit 3 — it exists purely to
exercise the CLI/state-machine wiring end to end before Commit 5 wraps the real
Hugging Face Z-Image-Turbo pipeline. `mediactl generate` refuses any adapter
name other than `stub` for now and says so, rather than pretending to work."""

from __future__ import annotations

AVAILABLE_ADAPTERS = {"stub"}
