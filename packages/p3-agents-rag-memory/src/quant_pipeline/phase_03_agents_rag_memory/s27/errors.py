"""Typed failures for P3.S27."""

class S27Error(Exception):
    """Base failure for emergence measurement."""

class S27ContractError(S27Error):
    """Input or output contract violation."""

class S27TemporalError(S27Error):
    """Point-in-time or cycle violation."""

class S27PolicyError(S27Error):
    """Configuration or authority violation."""

class S27CausalityError(S27Error):
    """Invalid causal graph or parent relationship."""
