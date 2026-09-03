"""Stable façade for the cohesive S30 product-building package.

Business logic lives in :mod:`runtime_products.s30`; this module preserves the
historical import path used by the module wrappers.
"""

from .runtime_products.s30 import (
    S30ContractError, S30Error, S30IntegrityError, S30LineageError,
    S30PrivacyError, S30TemporalError, build_context_memory_features,
    build_hypothesis_registry, build_phase4_social_handoff,
    build_social_features, build_variable_evolution_handoff,
)

__all__ = [
    "S30Error", "S30ContractError", "S30TemporalError", "S30LineageError",
    "S30PrivacyError", "S30IntegrityError", "build_social_features",
    "build_context_memory_features", "build_hypothesis_registry",
    "build_phase4_social_handoff", "build_variable_evolution_handoff",
]
