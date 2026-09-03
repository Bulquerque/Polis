from __future__ import annotations
from collections.abc import Mapping
from ..boundary import build_artifact, module_result, parse_artifact, parse_context
from ..subphases.s5_ltr_training.qualification import QualificationPolicy, qualify_models

MODULE_ID = "P7.S5.M05"

def run_module(inputs: Mapping[str, object], config: Mapping[str, object]) -> dict[str, object]:
    context = parse_context(config)
    models = parse_artifact(inputs.get("ltr_model_artifact"), name="ltr_model_artifact")
    oof = parse_artifact(inputs.get("ltr_oof_score_panel"), name="ltr_oof_score_panel")
    calibration = parse_artifact(inputs.get("ltr_calibration_evidence_panel"), name="ltr_calibration_evidence_panel")
    receipts = parse_artifact(inputs.get("training_execution_receipt"), name="training_execution_receipt")
    baseline = parse_artifact(inputs.get("interpretable_baseline_history"), name="interpretable_baseline_history")
    if baseline.content_sha256 != oof.content_sha256:
        # The baseline history is a separately named, byte-equivalent view of OOF records.
        baseline_by_key = {(r["model_family_id"], r["fold_id"], r["query_id"], r["candidate_id"]): r["interpretable_score"] for r in baseline.records}
        for row in oof.records:
            key = (row["model_family_id"], row["fold_id"], row["query_id"], row["candidate_id"])
            if key not in baseline_by_key or float(baseline_by_key[key]) != float(row["interpretable_score"]):
                raise ValueError("interpretable baseline history does not reconcile with OOF evidence")
    policy = QualificationPolicy.model_validate(config.get("qualification_policy"))
    reports, registry = qualify_models(models.records, oof.records, calibration.records, receipts.records, policy)
    outputs = {
        "ltr_model_qualification_report": build_artifact(name="ltr_model_qualification_report", producer_module_id=MODULE_ID, records=reports, context=context),
        "ltr_model_qualification_registry": build_artifact(name="ltr_model_qualification_registry", producer_module_id=MODULE_ID, records=registry, context=context),
    }
    return module_result(module_id=MODULE_ID, outputs=outputs, metrics={"qualified_count": sum(1 for row in registry if row["runtime_eligible"])})
