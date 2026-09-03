"""Registry and validation surface for P3.S25-P3.S28 society evolution."""
from .registry import SOCIETY_MODULES, SOCIETY_SUBPHASES, society_status
from .validation import require_valid_society_runtime, validate_society_runtime

__all__ = [
    "SOCIETY_MODULES",
    "SOCIETY_SUBPHASES",
    "society_status",
    "validate_society_runtime",
    "require_valid_society_runtime",
]
