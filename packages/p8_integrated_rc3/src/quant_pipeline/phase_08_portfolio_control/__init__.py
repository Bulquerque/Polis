"""Unified Phase 8 portfolio-control package."""

from .api import (
    P567RC3AdaptationResult,
    P567RC3Adapter,
    P567RC3CompatibilityError,
    adapt_p567_rc3_to_p8,
    run_s7,
    run_s8,
)
from .version import __version__

__all__ = [
    "P567RC3AdaptationResult",
    "P567RC3Adapter",
    "P567RC3CompatibilityError",
    "__version__",
    "adapt_p567_rc3_to_p8",
    "run_s7",
    "run_s8",
]
