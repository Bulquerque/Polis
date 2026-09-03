"""Typed exception hierarchy for integrity failures."""

class S3Error(Exception):
    """Base exception for P8.S3."""

class ContractIntegrityError(S3Error):
    """A public contract is inconsistent or incompatible."""

class TemporalIntegrityError(S3Error):
    """A record violates point-in-time constraints."""

class ProbabilityIntegrityError(S3Error):
    """Probabilities or distribution parameters are corrupt."""

class NumericalIntegrityError(S3Error):
    """Numerical output contains non-finite or impossible values."""

class LineageIntegrityError(S3Error):
    """Content identity or lineage does not close."""

class CapabilityUnavailableError(S3Error):
    """A caller requested a capability not supported by the evidence."""
