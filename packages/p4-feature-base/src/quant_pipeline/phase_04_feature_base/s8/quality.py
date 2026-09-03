from __future__ import annotations
from collections import defaultdict
import numpy as np
from quant_pipeline.common.hashing.hash_utils import canonical_sha256
from .artifacts import ArtifactEnvelope, ExecutionContext, build_artifact


def _cosine(left: np.ndarray, right: np.ndarray) -> float:
    denom = float(np.linalg.norm(left) * np.linalg.norm(right))
    return float(np.dot(left, right) / denom) if denom else 0.0


def build_quality_outputs(pca_states: ArtifactEnvelope, encoder_states: ArtifactEnvelope,
                          factors: ArtifactEnvelope, embeddings: ArtifactEnvelope,
                          context: ExecutionContext) -> dict[str, ArtifactEnvelope]:
    records: list[dict[str, object]] = []
    loading_groups: dict[tuple[str,str,str], list[np.ndarray]] = defaultdict(list)
    for state in pca_states.records:
        components = np.asarray(state["components"], dtype=float)
        key = (state["family_id"], state["horizon_group"], state["representation_type"])
        loading_groups[key].append(components.ravel())
        sparsity = float(np.mean(np.isclose(components, 0.0)))
        records.append({"representation_id":state["fit_state_id"],"family_id":state["family_id"],
            "horizon_group":state["horizon_group"],"representation_type":state["representation_type"],
            "fold_id":state["fold_id"],"reconstruction_rmse":state["validation_reconstruction_rmse"],
            "explained_variance_sum":float(sum(state["explained_variance_ratio"])),"loading_sparsity":sparsity,
            "converged":state["converged"],"quality_state":"VALIDATED" if state["converged"] else "DEGRADED"})
    stability: dict[str,float] = {}
    for key, values in loading_groups.items():
        scores = [_cosine(values[i-1], values[i]) for i in range(1,len(values)) if values[i-1].shape==values[i].shape]
        stability["|".join(key)] = float(np.mean(scores)) if scores else 1.0
    for state in encoder_states.records:
        shared_weights = np.asarray(state["model_state"]["weights"]["shared.0.weight"], dtype=float)
        records.append({"representation_id":state["fit_state_id"],"family_id":state["family_id"],
            "horizon_group":state["horizon_group"],"representation_type":"ENCODER","fold_id":state["fold_id"],
            "reconstruction_rmse":state["validation_reconstruction_rmse"],"explained_variance_sum":None,
            "loading_sparsity":float(np.mean(np.isclose(shared_weights,0.0))),"converged":True,
            "quality_state":"VALIDATED"})
    search_records = [item | {"fit_state_id":state["fit_state_id"],"fold_id":state["fold_id"],
        "family_id":state["family_id"],"horizon_group":state["horizon_group"]}
        for state in encoder_states.records for item in state["search_records"]]
    bundle_records = [{"artifact_name":factors.artifact_name,"artifact_id":factors.artifact_id,
        "execution_status":factors.execution_status,"record_count":factors.record_count},
        {"artifact_name":embeddings.artifact_name,"artifact_id":embeddings.artifact_id,
        "execution_status":embeddings.execution_status,"record_count":embeddings.record_count}]
    lineage = canonical_sha256({"pca":pca_states.artifact_id,"encoder":encoder_states.artifact_id})
    return {
      "representation_quality_report": build_artifact(artifact_name="representation_quality_report",schema_version="v14.9-rc1",
        producer_module_id="P4.S8.M04",context=context,grain=("representation_id",),records=records,lineage_id=lineage,
        metadata={"loading_stability":stability,"metrics_are_non_predictive":True}),
      "representation_horizon_bundle": build_artifact(artifact_name="representation_horizon_bundle",schema_version="v14.9-rc1",
        producer_module_id="P4.S8.M04",context=context,grain=("artifact_name",),records=bundle_records,lineage_id=lineage,
        metadata={"contains_payload_copies":False}),
      "encoder_hyperparameter_search_report": build_artifact(artifact_name="encoder_hyperparameter_search_report",schema_version="v14.9-rc1",
        producer_module_id="P4.S8.M04",context=context,grain=("fit_state_id","config_id"),records=search_records,lineage_id=lineage,
        metadata={"maximum_configurations":2,"selection_uses_future_alpha":False},
        execution_status=encoder_states.execution_status,quality_status=encoder_states.quality_status)}
