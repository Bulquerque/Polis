"""Typed errors for P9.S8."""


class S8Error(Exception):
    """Base class for S8 errors."""


class ContractError(S8Error):
    """Boundary contract violation."""


class AttributionInvariantError(S8Error):
    """Attribution or reconciliation invariant violation."""


class NumericalDomainError(S8Error):
    """Invalid numerical domain or non-finite calculation."""
