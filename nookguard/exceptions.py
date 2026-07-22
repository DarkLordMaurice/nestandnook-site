"""NookGuard exception hierarchy."""


class NookGuardError(Exception):
    """Base class for all NookGuard errors."""


class InvalidTransitionError(NookGuardError):
    """Raised when a state transition is not permitted by the state machine."""

    def __init__(self, from_state: str, to_state: str, asset_id: str = ""):
        self.from_state = from_state
        self.to_state = to_state
        self.asset_id = asset_id
        super().__init__(
            f"Illegal transition {from_state} -> {to_state}"
            + (f" for asset {asset_id}" if asset_id else "")
        )


class HashMismatchError(NookGuardError):
    """Raised when a computed hash does not match a recorded/expected hash."""

    def __init__(self, expected: str, actual: str, context: str = ""):
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Hash mismatch{f' ({context})' if context else ''}: "
            f"expected {expected}, got {actual}"
        )


class NarrativeOverrideError(NookGuardError):
    """Raised if a judgment payload contains a forbidden narrative-override field
    (e.g. extra_justification) — the doc's 'no narrative override' rule (29.5)."""


class ProtectedPathError(NookGuardError):
    """Raised when code attempts to write directly to a protected/public media
    path instead of going through the release workflow (hook H001/H008)."""


class MissingCanonError(NookGuardError):
    """Raised when a file listed in canon.CANON_FILES does not exist on disk.
    A compiler that silently proceeded without a canon file it believes it is
    honoring would be worse than one that fails loudly."""

    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__(f"Missing canon file(s): {', '.join(missing)}")


class StaleCanonError(NookGuardError):
    """H007: 'prompt compile includes superseded source -> fail compile'. The
    contract's canonical_reference_bundle_sha256 no longer matches the live
    canon bundle hash — canon changed underneath a locked spec."""

    def __init__(self, referenced: str, current: str):
        self.referenced = referenced
        self.current = current
        super().__init__(
            f"Stale canon reference: spec locked against {referenced}, "
            f"current canon bundle is {current}"
        )
