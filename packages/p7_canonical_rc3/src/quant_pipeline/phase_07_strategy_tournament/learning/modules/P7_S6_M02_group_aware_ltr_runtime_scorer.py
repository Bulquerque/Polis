from __future__ import annotations
from collections.abc import Mapping
from ..boundary import build_artifact, module_result, parse_artifact, parse_context
from ..subphases.s6_runtime_scoring.scoring import score_candidates

MODULE_ID = "P7.S6.M02"

def run_module(inputs: Mapping[str, object], config: Mapping[str, object]) -> dict[str, object]:
    context = parse_context(config)
    candidates = parse_artifact(inputs.get("factor_adjusted_candidate_panel"), name="factor_adjusted_candidate_panel")
    models = parse_artifact(inputs.get("ltr_model_artifact"), name="ltr_model_artifact")
    references = parse_artifact(inputs.get("resolved_runtime_model_reference"), name="resolved_runtime_model_reference")
    compatibility = parse_artifact(inputs.get("runtime_model_compatibility_report"), name="runtime_model_compatibility_report")
    scores, receipts = score_candidates(candidates.records, models.records, references.records, compatibility.records)
    outputs = {
        "ltr_model_score_panel": build_artifact(name="ltr_model_score_panel", producer_module_id=MODULE_ID, records=scores, context=context),
        "model_runtime_receipt": build_artifact(name="model_runtime_receipt", producer_module_id=MODULE_ID, records=receipts, context=context),
    }
    return module_result(module_id=MODULE_ID, outputs=outputs, metrics={"scored_count": sum(row["score_status"] == "SCORED" for row in scores), "candidate_count": len(scores)})
