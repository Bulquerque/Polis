from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

import yaml

from .boundary import build_artifact, parse_artifact, parse_context
from .modules import (
    P7_S5_M01_ranking_target_policy_registry_builder as m01,
    P7_S5_M02_counterfactual_training_dataset_builder as m02,
    P7_S5_M03_query_group_temporal_split_planner as m03,
    P7_S5_M04_ltr_training_orchestrator as m04,
    P7_S5_M05_ltr_model_qualification_gate as m05,
)


def _baseline_view(oof: dict[str, Any], config: Mapping[str, object]) -> dict[str, Any]:
    records = [dict(row) for row in parse_artifact(oof, name="ltr_oof_score_panel").records]
    return build_artifact(
        name="interpretable_baseline_history",
        producer_module_id="P7.S5.RUNNER",
        records=records,
        context=parse_context(config),
    )


def _merged_outputs(results: list[dict[str, Any]]) -> dict[str, Any]:
    outputs: dict[str, Any] = {}
    for result in results:
        outputs.update(result["outputs"])
    return outputs


def run_s5_pipeline(inputs: Mapping[str, object], config: Mapping[str, object]) -> dict[str, Any]:
    result_01 = m01.run_module(inputs, config)
    result_02 = m02.run_module(
        {
            "historical_tournament_snapshots": inputs["historical_tournament_snapshots"],
            "historical_candidate_counterfactual_outcome_panel": inputs["historical_candidate_counterfactual_outcome_panel"],
            "ranking_target_policy_registry": result_01["outputs"]["ranking_target_policy_registry"],
        },
        config,
    )
    result_03 = m03.run_module(
        {
            "ltr_training_dataset_manifest": result_02["outputs"]["ltr_training_dataset_manifest"],
            "trading_calendar_reference": inputs["trading_calendar_reference"],
        },
        config,
    )
    result_04 = m04.run_module(
        {
            "ltr_training_dataset_manifest": result_02["outputs"]["ltr_training_dataset_manifest"],
            "ltr_temporal_fold_plan": result_03["outputs"]["ltr_temporal_fold_plan"],
            "model_family_registry": inputs["model_family_registry"],
        },
        config,
    )
    result_05 = m05.run_module(
        {
            **result_04["outputs"],
            "interpretable_baseline_history": _baseline_view(
                result_04["outputs"]["ltr_oof_score_panel"], config
            ),
        },
        config,
    )
    results = [result_01, result_02, result_03, result_04, result_05]
    return {"subphase_id": "P7.S5", "status": "PASS", "module_results": results, "outputs": _merged_outputs(results)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run P7.S5 offline LTR pipeline")
    parser.add_argument("--input", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    inputs = json.loads(Path(args.input).read_text(encoding="utf-8"))
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    result = run_s5_pipeline(inputs, config)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
