from __future__ import annotations
from collections.abc import Mapping
from ..boundary import build_artifact, module_result, parse_artifact, parse_context
from ..subphases.s5_ltr_training.target_policy import compile_target_policies

MODULE_ID = "P7.S5.M01"

def run_module(inputs: Mapping[str, object], config: Mapping[str, object]) -> dict[str, object]:
    context = parse_context(config)
    source = parse_artifact(inputs.get("ranking_target_policy_source"), name="ranking_target_policy_source")
    semantics = parse_artifact(inputs.get("metric_semantics_registry"), name="metric_semantics_registry")
    records = compile_target_policies(source.records, semantics.records)
    output = build_artifact(name="ranking_target_policy_registry", producer_module_id=MODULE_ID, records=records, context=context)
    return module_result(module_id=MODULE_ID, outputs={"ranking_target_policy_registry": output}, metrics={"target_count": len(records)})
