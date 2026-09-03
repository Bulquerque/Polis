from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import TypeAdapter

from ..modules.P4_S7_M01_causal_transform_fit_engine import run_module as run_m01
from ..modules.P4_S7_M02_normalization_neutralization_engine import run_module as run_m02
from ..modules.P4_S7_M03_diversity_redundancy_analyzer import run_module as run_m03
from ..modules.P4_S7_M04_structural_feature_selector import run_module as run_m04
from .artifacts import ArtifactEnvelope, ExecutionContext


MODULE_SEQUENCE = (run_m01, run_m02, run_m03, run_m04)


def run_subphase(
    inputs: dict[str, ArtifactEnvelope], context: ExecutionContext
) -> dict[str, ArtifactEnvelope]:
    artifacts = dict(inputs)
    for module in MODULE_SEQUENCE:
        artifacts.update(module(artifacts, context))
    output_names = {
        "causally_transformed_feature_panel",
        "causal_transform_fit_state_manifest",
        "normalization_neutralization_fit_state_manifest",
        "underlying_feature_matrix_interpretable",
        "underlying_feature_matrix_raw",
        "feature_diversity_redundancy_report",
        "underlying_feature_matrix_selected",
        "feature_selection_report",
        "feature_transform_state_manifest",
    }
    return {name: artifacts[name] for name in sorted(output_names)}


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python -m quant_pipeline.phase_04_feature_base.s7.runner INPUT.json")
        return 2
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    context = ExecutionContext.model_validate(payload["context"])
    adapter = TypeAdapter(dict[str, ArtifactEnvelope])
    inputs = adapter.validate_python(payload["inputs"])
    outputs = run_subphase(inputs, context)
    print(json.dumps({name: value.model_dump(mode="json") for name, value in outputs.items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
