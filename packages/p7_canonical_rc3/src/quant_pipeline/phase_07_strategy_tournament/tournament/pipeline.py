from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .s3_runner import run_subphase as run_s3
from .s4_runner import run_subphase as run_s4


def run_tournament_pipeline(inputs: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    """Execute Tournament subphases S3 then S4 using a single canonical artifact flow."""
    s3_inputs = {key: value for key, value in inputs.items() if key != "scoring_policy_context"}
    s3_result = run_s3(s3_inputs, config)
    s4_inputs = dict(inputs)
    s4_inputs.update(s3_result["outputs"])
    s4_result = run_s4(s4_inputs, config)
    outputs = {**s3_result["outputs"], **s4_result["outputs"]}
    return {
        "phase": "P7",
        "stages": "TOURNAMENT",
        "subphases": ("P7.S3", "P7.S4"),
        "status": "PASS",
        "subphase_results": (s3_result, s4_result),
        "outputs": outputs,
    }
