class CompatibilityError(RuntimeError):
    """Base error for fail-closed cross-phase compatibility operations."""


class PhaseUnavailableError(CompatibilityError):
    """Raised when an optional phase implementation is not installed."""


class ContractMismatchError(CompatibilityError):
    """Raised when a producer payload does not match the frozen wire contract."""


class EvidenceIncompleteError(CompatibilityError):
    """Raised when a FULL handoff would require fabricating missing evidence."""
