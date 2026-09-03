"""Typed errors for P3.S6."""

class S6Error(Exception):
    """Base error for the subphase."""

class ContractError(S6Error):
    """A frozen input or output contract was violated."""

class ConfigurationError(S6Error):
    """Coverage or state-machine configuration is invalid."""

class StateCompatibilityError(S6Error):
    """An incompatible prior state cannot provide the information needed for deterministic metrics."""

class AccumulatorConflictError(S6Error):
    """The same candidate ID maps to different immutable content."""

class InvalidTransitionError(S6Error):
    """The generation state machine received an impossible transition."""
