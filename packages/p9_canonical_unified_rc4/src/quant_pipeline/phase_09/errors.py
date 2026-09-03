"""Shared typed errors for Phase 09.

Expected economic states belong in result contracts. These exceptions are
reserved for invalid contracts, integrity failures, unsupported capabilities,
numerical-domain violations, and impossible internal states.
"""

class P9Error(Exception):
    """Base class for unrecoverable Phase 09 errors."""


class ContractError(P9Error):
    """A boundary or domain contract is invalid."""


class IntegrityError(P9Error):
    """A content hash, manifest, or lineage integrity check failed."""


class TemporalIntegrityError(P9Error):
    """A point-in-time, maturity, or cycle-order invariant failed."""


class LineageIntegrityError(P9Error):
    """Required immutable lineage is missing or contradictory."""


class NumericalDomainError(P9Error):
    """A numerical method was requested outside its supported domain."""


class CapabilityError(P9Error):
    """A requested optional capability is unavailable."""


class InvariantViolation(P9Error):
    """An internal state invariant was violated."""


class ExecutionTimeoutError(P9Error):
    """A bounded execution exceeded its hard deadline."""
