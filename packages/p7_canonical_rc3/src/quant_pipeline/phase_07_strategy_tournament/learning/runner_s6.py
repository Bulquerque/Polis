from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any, Mapping
import yaml
from .modules import (
    P7_S6_M01_runtime_model_compatibility_gate as m01,
    P7_S6_M02_group_aware_ltr_runtime_scorer as m02,
    P7_S6_M03_score_calibration_confidence_engine as m03,
    P7_S6_M04_hybrid_score_blend_and_handoff_builder as m04,
)

def _merged(results: list[dict[str, Any]]) -> dict[str, Any]:
    outputs: dict[str, Any] = {}
    for result in results: outputs.update(result["outputs"])
    return outputs

def run_s6_pipeline(inputs: Mapping[str, object], config: Mapping[str, object]) -> dict[str, Any]:
    result_01 = m01.run_module(inputs, config)
    result_02 = m02.run_module({
        "factor_adjusted_candidate_panel": inputs["factor_adjusted_candidate_panel"],
        "ltr_model_artifact": inputs["ltr_model_artifact"],
        **result_01["outputs"],
    }, config)
    result_03 = m03.run_module({
        "factor_adjusted_candidate_panel": inputs["factor_adjusted_candidate_panel"],
        "ltr_model_artifact": inputs["ltr_model_artifact"],
        "ltr_model_qualification_report": inputs["ltr_model_qualification_report"],
        **result_01["outputs"], **result_02["outputs"],
    }, config)
    result_04 = m04.run_module({
        "interpretable_score_panel": inputs["interpretable_score_panel"],
        "interpretable_score_decomposition_panel": inputs["interpretable_score_decomposition_panel"],
        **result_01["outputs"], **result_02["outputs"], **result_03["outputs"],
    }, config)
    results = [result_01, result_02, result_03, result_04]
    return {"subphase_id": "P7.S6", "status": "PASS", "module_results": results, "outputs": _merged(results)}

def main() -> None:
    parser = argparse.ArgumentParser(description="Run P7.S6 runtime LTR and hybrid scoring")
    parser.add_argument("--input", required=True); parser.add_argument("--config", required=True); parser.add_argument("--output", required=True)
    args = parser.parse_args()
    inputs = json.loads(Path(args.input).read_text(encoding="utf-8"))
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    result = run_s6_pipeline(inputs, config)
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
if __name__ == "__main__": main()
