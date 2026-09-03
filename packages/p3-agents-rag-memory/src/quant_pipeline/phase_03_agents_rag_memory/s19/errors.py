from __future__ import annotations


class S19Error(RuntimeError):
    """Base error for P3.S19."""


class S19InputError(S19Error):
    """Raised when a declared input violates its contract."""


class S19TemporalError(S19Error):
    """Raised when a temporal invariant is violated."""


class S19HashMismatchError(S19Error):
    """Raised when an input content hash does not match its payload."""


class S19PopulationMismatchError(S19Error):
    """Raised when population, seed and state identities do not align."""


class S19ForbiddenFieldError(S19Error):
    """Raised when a forbidden authority field is present."""
