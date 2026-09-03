"""Typed exceptions for P9.S7.

Expected economic states are represented by result statuses, not exceptions.
Exceptions are reserved for invalid contracts, temporal violations, integrity
failures, unsupported capabilities, and internal invariants.
"""

from __future__ import annotations


class S7Error(Exception):
    """Base class for P9.S7 errors."""


class ContractError(S7Error):
    """Input or output contract is semantically invalid."""


class TemporalIntegrityError(S7Error):
    """A point-in-time or maturity invariant was violated."""


class LineageIntegrityError(S7Error):
    """An immutable lineage reference is missing or contradictory."""


class NumericalDomainError(S7Error):
    """A numerical method was requested outside its supported domain."""


class CapabilityError(S7Error):
    """An optional capability was requested but is not available."""


class InvariantViolation(S7Error):
    """An internal state invariant was violated."""
