"""Typed failures for P3.S26."""

class S26Error(RuntimeError):
    """Base P3.S26 failure."""

class S26ContractError(S26Error):
    """Declared input or output contract is invalid."""

class S26TemporalError(S26Error):
    """Point-in-time or cycle invariant is invalid."""

class S26PolicyError(S26Error):
    """A policy attempted forbidden authority."""

class S26LineageError(S26Error):
    """Lineage or append-only history is invalid."""

class S26PersistenceError(S26Error):
    """Checkpoint persistence or restoration failed."""
