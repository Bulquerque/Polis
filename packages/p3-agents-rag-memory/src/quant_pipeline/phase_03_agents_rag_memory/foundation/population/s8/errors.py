"""Typed failures for P3.S8."""

class S8Error(Exception):
    """Base failure for initial social graph construction."""

class ContractError(S8Error):
    """An input, output or hash binding violates the frozen contract."""

class ConfigurationError(S8Error):
    """The social graph configuration is inconsistent or impossible."""

class GraphConstructionError(S8Error):
    """A deterministic graph satisfying mandatory constraints cannot be built."""

class IntegrityError(S8Error):
    """A content-addressed identifier, metric or reciprocal edge is inconsistent."""
