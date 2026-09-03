"""P7 Strategy Tournament — Learning integrated offline/runtime package."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

def run_s5_pipeline(inputs: Mapping[str, object], config: Mapping[str, object]) -> dict[str, Any]:
    """Execute P7.S5 offline LTR training and qualification."""
    from .runner_s5 import run_s5_pipeline as execute
    return execute(inputs, config)

def run_s6_pipeline(inputs: Mapping[str, object], config: Mapping[str, object]) -> dict[str, Any]:
    """Execute P7.S6 runtime LTR scoring and hybrid blend."""
    from .runner_s6 import run_s6_pipeline as execute
    return execute(inputs, config)

def build_s6_input_bundle(
    tournament_runtime_inputs: Mapping[str, object],
    s5_outputs: Mapping[str, object],
    governed_model_registry: object,
) -> dict[str, object]:
    """Build the immutable P7.S6 input bundle without promoting a model."""
    from .integration import build_s6_input_bundle as build
    return build(tournament_runtime_inputs, s5_outputs, governed_model_registry)

def run_learning_pipeline(
    offline_inputs: Mapping[str, object],
    offline_config: Mapping[str, object],
    tournament_runtime_inputs: Mapping[str, object],
    governed_model_registry: object,
    runtime_config: Mapping[str, object],
) -> dict[str, Any]:
    """Run S5 then S6; P0 governance remains an explicit external input."""
    from .integration import run_learning_pipeline as execute
    return execute(
        offline_inputs,
        offline_config,
        tournament_runtime_inputs,
        governed_model_registry,
        runtime_config,
    )

__all__ = [
    "build_s6_input_bundle",
    "run_learning_pipeline",
    "run_s5_pipeline",
    "run_s6_pipeline",
]

__version__ = "2.3.1rc3.post2"
