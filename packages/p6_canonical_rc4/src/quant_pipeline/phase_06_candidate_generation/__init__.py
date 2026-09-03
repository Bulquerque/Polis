"""Stable external alias for the canonical P6 strategy-synthesis engine.

This package contains no independent implementation. It preserves the general
project import path while delegating to the single authoritative P6 runner.
"""
from quant_pipeline.phase_06_strategy_synthesis import run_phase

__all__ = ["run_phase"]
