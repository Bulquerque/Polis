"""Stable facade for P6.S4 mutation services."""

from .mutation_engine import mutate_candidates
from .operator_registry import operator_registry
from .validation import complexity_gate, validate_mutation_traces

__all__ = (
    "complexity_gate",
    "mutate_candidates",
    "operator_registry",
    "validate_mutation_traces",
)
