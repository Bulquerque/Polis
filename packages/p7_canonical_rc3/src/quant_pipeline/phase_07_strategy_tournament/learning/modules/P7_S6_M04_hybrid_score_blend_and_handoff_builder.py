from __future__ import annotations
from collections.abc import Mapping
from ..boundary import build_artifact, module_result, parse_artifact, parse_context
from ..subphases.s6_runtime_scoring.blend import build_handoff_manifest, build_hybrid_outputs
from ..subphases.s6_runtime_scoring.contracts import BlendPolicy, ConfidencePolicy

MODULE_ID = "P7.S6.M04"

def run_module(inputs: Mapping[str, object], config: Mapping[str, object]) -> dict[str, object]:
    context = parse_context(config)
    interpret = parse_artifact(inputs.get("interpretable_score_panel"), name="interpretable_score_panel")
    decomposition = parse_artifact(inputs.get("interpretable_score_decomposition_panel"), name="interpretable_score_decomposition_panel")
    model_scores = parse_artifact(inputs.get("ltr_model_score_panel"), name="ltr_model_score_panel")
    runtime_receipt = parse_artifact(inputs.get("model_runtime_receipt"), name="model_runtime_receipt")
    calibration = parse_artifact(inputs.get("ltr_score_calibration_panel"), name="ltr_score_calibration_panel")
    confidence = parse_artifact(inputs.get("ltr_score_confidence_panel"), name="ltr_score_confidence_panel")
    compatibility = parse_artifact(inputs.get("runtime_model_compatibility_report"), name="runtime_model_compatibility_report")
    blend = BlendPolicy.model_validate(config.get("blend_policy"))
    confidence_policy = ConfidencePolicy.model_validate(config.get("confidence_policy"))
    hybrid, parts, conservation = build_hybrid_outputs(interpret.records, decomposition.records,
                                                        calibration.records, confidence.records,
                                                        compatibility.records, blend, confidence_policy)
    outputs = {
        "hybrid_candidate_score_panel": build_artifact(name="hybrid_candidate_score_panel", producer_module_id=MODULE_ID, records=hybrid, context=context),
        "hybrid_score_decomposition_panel": build_artifact(name="hybrid_score_decomposition_panel", producer_module_id=MODULE_ID, records=parts, context=context),
        "learning_candidate_conservation_report": build_artifact(name="learning_candidate_conservation_report", producer_module_id=MODULE_ID, records=conservation, context=context),
    }
    manifest_records = build_handoff_manifest({**outputs,
        "runtime_model_compatibility_report": compatibility.model_dump(mode="json"),
        "ltr_model_score_panel": model_scores.model_dump(mode="json"),
        "ltr_score_calibration_panel": calibration.model_dump(mode="json"),
        "ltr_score_confidence_panel": confidence.model_dump(mode="json"),
        "model_runtime_receipt": runtime_receipt.model_dump(mode="json"),
    }, contract_version=str(config.get("learning_handoff_contract_version", "1.0.0")))
    outputs["hybrid_scoring_handoff_manifest"] = build_artifact(name="hybrid_scoring_handoff_manifest", producer_module_id=MODULE_ID, records=manifest_records, context=context)
    return module_result(module_id=MODULE_ID, outputs=outputs, metrics={"candidate_count": len(hybrid), "hybrid_count": sum(row["hybrid_status"] == "HYBRID" for row in hybrid)})
