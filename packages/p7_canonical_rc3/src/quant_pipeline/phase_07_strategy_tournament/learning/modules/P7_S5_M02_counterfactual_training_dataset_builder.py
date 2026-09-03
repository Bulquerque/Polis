from __future__ import annotations
from collections.abc import Mapping
from ..boundary import build_artifact, module_result, parse_artifact, parse_context
from ..subphases.s5_ltr_training.dataset import DatasetPolicy, build_training_dataset

MODULE_ID = "P7.S5.M02"

def run_module(inputs: Mapping[str, object], config: Mapping[str, object]) -> dict[str, object]:
    context = parse_context(config)
    snapshots = parse_artifact(inputs.get("historical_tournament_snapshots"), name="historical_tournament_snapshots")
    outcomes = parse_artifact(inputs.get("historical_candidate_counterfactual_outcome_panel"), name="historical_candidate_counterfactual_outcome_panel")
    registry = parse_artifact(inputs.get("ranking_target_policy_registry"), name="ranking_target_policy_registry")
    policy = DatasetPolicy.model_validate(config.get("dataset_policy"))
    rows, queries, coverage = build_training_dataset(snapshots.records, outcomes.records, registry.records, policy, current_cycle_id=context.cycle_id)
    outputs = {
        "ltr_training_dataset_manifest": build_artifact(name="ltr_training_dataset_manifest", producer_module_id=MODULE_ID, records=rows, context=context),
        "ltr_query_group_panel": build_artifact(name="ltr_query_group_panel", producer_module_id=MODULE_ID, records=queries, context=context),
        "label_coverage_report": build_artifact(name="label_coverage_report", producer_module_id=MODULE_ID, records=coverage, context=context),
    }
    return module_result(module_id=MODULE_ID, outputs=outputs, metrics={"row_count": len(rows), "query_count": len(queries)})
