"""Cohesive S30 product builders."""

from .common import (
    S30ContractError, S30Error, S30IntegrityError, S30LineageError,
    S30PrivacyError, S30TemporalError,
)
from .context_memory import build_context_memory_features
from .handoffs import build_phase4_social_handoff, build_variable_evolution_handoff
from .hypotheses import build_hypothesis_registry
from .social import build_social_features

__all__ = [
    "S30Error", "S30ContractError", "S30TemporalError", "S30LineageError",
    "S30PrivacyError", "S30IntegrityError", "build_social_features",
    "build_context_memory_features", "build_hypothesis_registry",
    "build_phase4_social_handoff", "build_variable_evolution_handoff",
]
