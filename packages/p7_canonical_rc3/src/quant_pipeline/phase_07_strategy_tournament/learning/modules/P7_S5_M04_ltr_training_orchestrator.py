from __future__ import annotations
from collections.abc import Mapping
from ..boundary import build_artifact, module_result, parse_artifact, parse_context
from ..subphases.s5_ltr_training.training import ResearchBudget, train_models

MODULE_ID = "P7.S5.M04"

def run_module(inputs: Mapping[str, object], config: Mapping[str, object]) -> dict[str, object]:
    context = parse_context(config)
    dataset = parse_artifact(inputs.get("ltr_training_dataset_manifest"), name="ltr_training_dataset_manifest")
    folds = parse_artifact(inputs.get("ltr_temporal_fold_plan"), name="ltr_temporal_fold_plan")
    families = parse_artifact(inputs.get("model_family_registry"), name="model_family_registry")
    budget = ResearchBudget.model_validate(config.get("research_budget"))
    models, oof, calibration, receipts = train_models(dataset.records, folds.records, families.records, budget, seed=int(config.get("seed", 0)), training_cutoff_at=str(config["training_cutoff_at"]))
    outputs = {
        "ltr_model_artifact": build_artifact(name="ltr_model_artifact", producer_module_id=MODULE_ID, records=models, context=context),
        "ltr_oof_score_panel": build_artifact(name="ltr_oof_score_panel", producer_module_id=MODULE_ID, records=oof, context=context),
        "ltr_calibration_evidence_panel": build_artifact(name="ltr_calibration_evidence_panel", producer_module_id=MODULE_ID, records=calibration, context=context),
        "training_execution_receipt": build_artifact(name="training_execution_receipt", producer_module_id=MODULE_ID, records=receipts, context=context),
    }
    return module_result(module_id=MODULE_ID, outputs=outputs, metrics={"model_count": len(models), "oof_count": len(oof)})
