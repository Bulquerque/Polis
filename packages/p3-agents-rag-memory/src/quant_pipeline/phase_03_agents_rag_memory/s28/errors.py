"""Typed failures for P3.S28."""

class S28Error(Exception):
    """Base error for the subphase."""


class S28ContractError(S28Error):
    """An input, output, or configuration violates a declared contract."""


class S28TemporalError(S28ContractError):
    """An artifact violates point-in-time semantics."""


class S28QualityError(S28Error):
    """Quality assessment could not be performed safely."""
