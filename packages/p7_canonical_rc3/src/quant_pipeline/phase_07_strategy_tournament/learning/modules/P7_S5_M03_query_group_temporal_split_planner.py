from __future__ import annotations
from collections.abc import Mapping
from ..boundary import build_artifact, module_result, parse_artifact, parse_context
from ..subphases.s5_ltr_training.temporal_split import SplitPolicy, build_temporal_folds

MODULE_ID = "P7.S5.M03"

def run_module(inputs: Mapping[str, object], config: Mapping[str, object]) -> dict[str, object]:
    context = parse_context(config)
    dataset = parse_artifact(inputs.get("ltr_training_dataset_manifest"), name="ltr_training_dataset_manifest")
    calendar = parse_artifact(inputs.get("trading_calendar_reference"), name="trading_calendar_reference")
    policy = SplitPolicy.model_validate(config.get("split_policy"))
    folds = build_temporal_folds(dataset.records, calendar.records, policy)
    output = build_artifact(name="ltr_temporal_fold_plan", producer_module_id=MODULE_ID, records=folds, context=context)
    return module_result(module_id=MODULE_ID, outputs={"ltr_temporal_fold_plan": output}, metrics={"fold_count": len(folds)})
