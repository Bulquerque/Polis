"""Typed failures for P3.S7."""

class S7Error(Exception):
    """Base error for the fixed-population subphase."""

class ContractError(S7Error):
    """A frozen input/output contract or hash binding was violated."""

class ConfigurationError(S7Error):
    """Population representation configuration is internally inconsistent."""

class PopulationConstructionError(S7Error):
    """A deterministic population could not be constructed from the finalized pool."""

class IntegrityError(S7Error):
    """Content-addressed identifiers or manifests do not recompute exactly."""
