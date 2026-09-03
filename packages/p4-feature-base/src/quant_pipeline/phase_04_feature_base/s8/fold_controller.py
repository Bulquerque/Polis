from __future__ import annotations
from datetime import datetime
from quant_pipeline.common.hashing.hash_utils import canonical_sha256
from .artifacts import ArtifactEnvelope, ExecutionContext, build_artifact
from .folds import build_fold_records
from .matrix import build_group_matrices
from .records import RepresentationPolicy


def build_fold_artifacts(matrix: ArtifactEnvelope, policy: RepresentationPolicy, context: ExecutionContext) -> dict[str, ArtifactEnvelope]:
    times = tuple(sorted({datetime.fromisoformat(str(r["decision_time"]).replace("Z", "+00:00")) for r in matrix.records}))
    fold_records = build_fold_records(times, policy)
    groups = build_group_matrices(matrix)
    row_count = sum(group.values.shape[0] for group in groups)
    modality_count = len({name for group in groups for name in group.modalities})
    feature_count = len({feature for group in groups for feature in group.feature_ids})
    if not policy.encoder_requested:
        decision, reason = "NOT_REQUESTED", "encoder_requested_false"
    elif row_count < policy.encoder_min_train_rows:
        decision, reason = "NOT_ENOUGH_DATA", "row_count_below_policy"
    elif modality_count < policy.encoder_min_modalities:
        decision, reason = "NOT_ENOUGH_MODALITIES", "modality_count_below_policy"
    else:
        decision, reason = "AUTHORIZED", "structural_preconditions_passed"
    config_records = [item.model_dump(mode="json") for item in policy.encoder_configurations]
    lineage = canonical_sha256({"matrix":matrix.artifact_id,"policy":policy.model_dump(mode="json")})
    common = dict(context=context, schema_version="v14.9-rc1", lineage_id=lineage)
    return {
      "representation_fold_plan": build_artifact(artifact_name="representation_fold_plan",producer_module_id="P4.S8.M01",
        grain=("fold_id",),records=fold_records,metadata={"source_matrix_id":matrix.artifact_id},**common),
      "encoder_hyperparameter_search_plan": build_artifact(artifact_name="encoder_hyperparameter_search_plan",producer_module_id="P4.S8.M01",
        grain=("config_id",),records=config_records,metadata={"maximum_configurations":2},**common),
      "encoder_execution_decision": build_artifact(artifact_name="encoder_execution_decision",producer_module_id="P4.S8.M01",
        grain=("decision",),records=[{"decision":decision,"reason":reason,"row_count":row_count,"feature_count":feature_count,
        "modality_count":modality_count}],metadata={},**common)}
