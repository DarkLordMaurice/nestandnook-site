# NookGuard — Claude-Only Media Reliability Control Plane

This directory is the governing implementation handoff for NookGuard, per Appendix M
of `NookGuard-Plan.docx` (the full 53-page source document, kept in this folder).

**Build objective (verbatim from Appendix M):** Implement NookGuard so Claude can
continue operating the Nest & Nook automation end to end without another AI provider,
while preventing one Claude session from self-certifying media, preventing unreviewed
bytes from entering pages, preventing stale bytes from being mistaken for production
success, and preserving exact evidence for every run.

Maurice's directive (2026-07-21): size of the build does not matter, pre-push owner
gating is deferred ("we'll get to that when it's time" — do not block on it), and the
build should start now because untrusted, unreviewed image generation is the actual
bottleneck slowing site development.

## Status

See `BUILD-LOG.md` in this folder for the running, evidence-backed record of what's
actually been built vs. planned. Do not trust this README's own prose over that log —
the log is updated per commit with file paths, test results, and commit hashes.
