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
