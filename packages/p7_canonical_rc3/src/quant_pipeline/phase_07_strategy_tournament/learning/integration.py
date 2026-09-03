from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

S5_TO_S6_ARTIFACTS = (
    "ltr_model_artifact",
    "ltr_model_qualification_registry",
    "ltr_model_qualification_report",
)

def build_s6_input_bundle(
    tournament_runtime_inputs: Mapping[str, object],
    s5_outputs: Mapping[str, object],
    governed_model_registry: object,
) -> dict[str, object]:
    """Join frozen S5 outputs with Tournament runtime artifacts and P0 governance."""
    result = deepcopy(dict(tournament_runtime_inputs))
    missing = [name for name in S5_TO_S6_ARTIFACTS if name not in s5_outputs]
    if missing:
        raise KeyError(f"missing S5 runtime artifacts: {missing}")
    for name in S5_TO_S6_ARTIFACTS:
        result[name] = deepcopy(s5_outputs[name])
    result["governed_model_registry"] = deepcopy(governed_model_registry)
    return result

def run_learning_pipeline(
    offline_inputs: Mapping[str, object],
    offline_config: Mapping[str, object],
    tournament_runtime_inputs: Mapping[str, object],
    governed_model_registry: object,
    runtime_config: Mapping[str, object],
) -> dict[str, Any]:
    """Execute the offline and runtime branches without hidden model promotion."""
    from .runner_s5 import run_s5_pipeline
    from .runner_s6 import run_s6_pipeline

    s5_result = run_s5_pipeline(offline_inputs, offline_config)
    s6_inputs = build_s6_input_bundle(
        tournament_runtime_inputs,
        s5_result["outputs"],
        governed_model_registry,
    )
    s6_result = run_s6_pipeline(s6_inputs, runtime_config)
    return {
        "stage_id": "LEARNING",
        "status": "PASS",
        "subphases": {"P7.S5": s5_result, "P7.S6": s6_result},
    }
