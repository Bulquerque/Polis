"""Typed exceptions for failures that prevent computation."""

class S3Error(Exception):
    """Base exception for P9.S3."""


class ContractError(S3Error):
    """Input or output contract is invalid."""


class TemporalIntegrityError(S3Error):
    """Point-in-time or temporal invariant failed."""


class ReplayIntegrityError(S3Error):
    """Deterministic replay or accounting reconciliation failed."""


class MetricPolicyError(S3Error):
    """Competition metric policy is unknown or inconsistent."""


class CapabilityUnavailableError(S3Error):
    """A required runner or capability is unavailable."""
