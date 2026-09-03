"""Stable external alias for the canonical P7 strategy-tournament engine.

The alias intentionally re-exports the public API only; no ranking logic is
duplicated here.
"""
from quant_pipeline.phase_07_strategy_tournament import (
    run_foundation_from_p6,
    run_offline_ltr,
    run_phase7,
    run_phase7_from_p6_result,
    run_runtime_from_foundation,
)

__all__ = [
    "run_foundation_from_p6",
    "run_runtime_from_foundation",
    "run_phase7",
    "run_phase7_from_p6_result",
    "run_offline_ltr",
]
