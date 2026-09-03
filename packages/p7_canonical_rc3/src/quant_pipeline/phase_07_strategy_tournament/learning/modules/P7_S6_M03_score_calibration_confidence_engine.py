from __future__ import annotations
from collections.abc import Mapping
from ..boundary import build_artifact, module_result, parse_artifact, parse_context
from ..domain.errors import fail
from ..subphases.s6_runtime_scoring.calibration import calibrate_and_confidence
from ..subphases.s6_runtime_scoring.contracts import ConfidencePolicy

MODULE_ID = "P7.S6.M03"

def run_module(inputs: Mapping[str, object], config: Mapping[str, object]) -> dict[str, object]:
    context = parse_context(config)
    candidates = parse_artifact(inputs.get("factor_adjusted_candidate_panel"), name="factor_adjusted_candidate_panel")
    scores = parse_artifact(inputs.get("ltr_model_score_panel"), name="ltr_model_score_panel")
    models = parse_artifact(inputs.get("ltr_model_artifact"), name="ltr_model_artifact")
    references = parse_artifact(inputs.get("resolved_runtime_model_reference"), name="resolved_runtime_model_reference")
    reports = parse_artifact(inputs.get("ltr_model_qualification_report"), name="ltr_model_qualification_report")
    if reports.available_at > context.decision_time:
        fail("P7_LTR_RUNTIME_ARTIFACT_FUTURE_DATED", "qualification report unavailable at decision time")
    policy = ConfidencePolicy.model_validate(config.get("confidence_policy"))
    calibrated, confidence = calibrate_and_confidence(candidates.records, scores.records, models.records,
                                                       references.records, reports.records, policy)
    outputs = {
        "ltr_score_calibration_panel": build_artifact(name="ltr_score_calibration_panel", producer_module_id=MODULE_ID, records=calibrated, context=context),
        "ltr_score_confidence_panel": build_artifact(name="ltr_score_confidence_panel", producer_module_id=MODULE_ID, records=confidence, context=context),
    }
    return module_result(module_id=MODULE_ID, outputs=outputs, metrics={"calibrated_count": sum(row["calibration_status"] == "CALIBRATED" for row in calibrated), "candidate_count": len(calibrated)})
