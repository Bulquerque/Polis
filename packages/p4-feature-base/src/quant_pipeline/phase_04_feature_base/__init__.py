"""Integrated Phase 4 feature-base implementation (S1-S9)."""

from .errors import BoundaryContractError, BoundaryErrorCode
from .integrated_runner import (
    run_foundation_to_fusion,
    run_integrated_phase,
    run_transform_to_assurance,
)
from .models import CompatibilityMode, ExecutionContext, ExecutionProfile
from .runtime.domain_error import P4DomainError
from .temporal import TemporalContractError, TemporalErrorCode

__version__ = "14.9.1"

__all__ = [
    "BoundaryContractError",
    "BoundaryErrorCode",
    "CompatibilityMode",
    "ExecutionContext",
    "ExecutionProfile",
    "P4DomainError",
    "TemporalContractError",
    "TemporalErrorCode",
    "run_foundation_to_fusion",
    "run_transform_to_assurance",
    "run_integrated_phase",
]
