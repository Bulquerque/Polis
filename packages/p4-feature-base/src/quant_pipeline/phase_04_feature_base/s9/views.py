from __future__ import annotations

from typing import Any

from quant_pipeline.common.hashing.hash_utils import canonical_sha256

from .artifacts import ArtifactEnvelope, ExecutionContext, build_artifact
from .records import ConsumerViewPolicy

VIEW_SPECS: dict[str, dict[str, Any]] = {
    "TABULAR_INTERPRETABLE": {
        "artifacts": ("underlying_feature_matrix_selected",),
        "grain": ("decision_time", "entity_id", "horizon_group"),
        "filters": (),
        "missingness": "preserve_explicit_mask",
    },
    "CROSS_SECTIONAL_RANKED": {
        "artifacts": ("underlying_feature_matrix_selected",),
        "grain": ("decision_time", "entity_id", "horizon_group"),
        "filters": ("normalized_values",),
        "missingness": "preserve_explicit_mask",
    },
    "SEQUENCE_MULTI_HORIZON": {
        "artifacts": (
            "underlying_feature_matrix_selected",
            "representation_fold_plan",
        ),
        "grain": ("entity_id", "decision_time", "horizon_group"),
        "filters": (),
        "missingness": "mask_and_age_of_information",
    },
    "GRAPH_RELATIONAL": {
        "artifacts": (),
        "grain": ("decision_time", "node_id", "edge_id"),
        "filters": ("requires_relational_graph_upstream",),
        "missingness": "unavailable_upstream",
    },
    "TAIL_RISK_SPECIALIST": {
        "artifacts": (
            "underlying_feature_matrix_selected",
            "underlying_feature_factors_pca",
        ),
        "grain": ("decision_time", "entity_id", "horizon_group"),
        "filters": ("family_contains:risk|tail|volatility|stress",),
        "missingness": "preserve_explicit_mask",
    },
    "REGIME_CONTEXT": {
        "artifacts": (
            "underlying_feature_matrix_selected",
            "underlying_feature_factors_pca",
        ),
        "grain": ("decision_time", "entity_id", "horizon_group"),
        "filters": ("family_contains:macro|regime|cycle|structure",),
        "missingness": "preserve_explicit_mask",
    },
    "LATENT_FAMILY": {
        "artifacts": (
            "underlying_feature_factors_pca",
            "underlying_feature_embeddings",
        ),
        "grain": (
            "decision_time",
            "entity_id",
            "family_id",
            "horizon_group",
        ),
        "filters": (),
        "missingness": "encoder_may_be_explicitly_skipped",
    },
    "SPARSE_MODALITY_AWARE": {
        "artifacts": ("underlying_feature_matrix_selected",),
        "grain": ("decision_time", "entity_id", "horizon_group"),
        "filters": ("missingness_mask", "source_modalities"),
        "missingness": "first_class_input",
    },
}


def _blocked_families(gate: ArtifactEnvelope) -> set[str]:
    return {
        str(record["scope_id"])
        for record in gate.records
        if record["gate_scope"] == "FAMILY"
        and record["decision"] == "BLOCK_FAMILY"
    }


def _view_records(
    view_id: str,
    inputs: dict[str, ArtifactEnvelope],
    policy: ConsumerViewPolicy,
    blocked: set[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    spec = VIEW_SPECS[view_id]
    artifact_names = [name for name in spec["artifacts"] if name in inputs]
    unavailable = not artifact_names
    status = "UNAVAILABLE_UPSTREAM" if unavailable else "PRODUCED"
    limitations = (
        ["required upstream relational graph is not available"]
        if unavailable
        else []
    )
    if blocked:
        limitations.append("blocked families excluded: " + ",".join(sorted(blocked)))
    references = [
        {
            "artifact_name": name,
            "artifact_id": inputs[name].artifact_id,
            "content_hash": inputs[name].content_hash,
            "record_count": inputs[name].record_count,
            "execution_status": inputs[name].execution_status,
        }
        for name in artifact_names
    ]
    manifest = {
        "view_id": view_id,
        "execution_status": status,
        "artifact_ids": [item["artifact_id"] for item in references],
        "grain": list(spec["grain"]),
        "feature_filters": list(spec["filters"]),
        "missingness_policy": spec["missingness"],
        "materialized": policy.materialize_payloads and not unavailable,
        "limitations": limitations,
    }
    bundle = {
        "view_id": view_id,
        "execution_status": status,
        "artifact_references": references,
        "payload_copied": False,
    }
    return manifest, bundle


def build_consumer_views(
    inputs: dict[str, ArtifactEnvelope],
    policy: ConsumerViewPolicy,
    gate: ArtifactEnvelope,
    context: ExecutionContext,
) -> dict[str, ArtifactEnvelope]:
    blocked = _blocked_families(gate)
    pairs = [
        _view_records(view_id, inputs, policy, blocked)
        for view_id in policy.enabled_views
    ]
    manifest_records = [pair[0] for pair in pairs]
    bundle_records = [pair[1] for pair in pairs]
    lineage = canonical_sha256(
        {
            "policy": policy.model_dump(mode="json"),
            "artifacts": sorted(item.artifact_id for item in inputs.values()),
        }
    )
    return {
        "model_consumer_view_manifest": build_artifact(
            artifact_name="model_consumer_view_manifest",
            schema_version="v14.9-rc1",
            producer_module_id="P4.S9.M03",
            context=context,
            grain=("view_id",),
            records=manifest_records,
            lineage_id=lineage,
            metadata={
                "contains_predictions": False,
                "blocked_families": sorted(blocked),
            },
        ),
        "model_consumer_view_bundle": build_artifact(
            artifact_name="model_consumer_view_bundle",
            schema_version="v14.9-rc1",
            producer_module_id="P4.S9.M03",
            context=context,
            grain=("view_id",),
            records=bundle_records,
            lineage_id=lineage,
            metadata={"contains_payload_copies": False},
        ),
    }
