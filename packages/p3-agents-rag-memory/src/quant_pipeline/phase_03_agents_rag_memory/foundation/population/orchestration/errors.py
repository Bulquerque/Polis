"""Errors raised by the population orchestration boundary."""


class PopulationCompatibilityError(ValueError):
    """Raised when a versioned artifact cannot cross a population subphase boundary."""


class PopulationPipelineBlockedError(RuntimeError):
    """Raised by callers that require a READY population pipeline result."""
