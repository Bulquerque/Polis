"""Typed errors for P8.S4 integrity, capability, and numerical failures."""
from __future__ import annotations


class S4Error(Exception):
    """Base error for the risk-state subphase."""


class ContractIntegrityError(S4Error):
    """A public or internal contract is inconsistent."""


class TemporalIntegrityError(S4Error):
    """Point-in-time or clock semantics were violated."""


class NumericalIntegrityError(S4Error):
    """Numerical arrays or calculations are invalid."""


class HashMismatchError(S4Error):
    """An artifact hash differs from the declared hash."""


class ValuationCapabilityError(S4Error):
    """A candidate cannot be valued with qualified evidence."""


class DualBookReconciliationError(S4Error):
    """Virtual candidate positions do not reconcile to physical positions."""


class MarginCapabilityError(S4Error):
    """No qualified margin method is available for a required candidate."""
