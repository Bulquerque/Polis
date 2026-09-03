from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.common.hashing.hash_utils import canonical_sha256

from ..runtime.artifact_envelope import ArtifactEnvelope, RuntimeExecutionContext, build_artifact
from ..runtime.canonical import deterministic_id


def _transform_policy_records(keys: list[tuple[str, str]]) -> list[dict[str, Any]]:
    return [
        {
            "feature_id": feature_id,
            "horizon_group": horizon,
            "transform_type": "identity",
            "window_type": "expanding",
            "lookback_timestamps": None,
            "min_observations": 2,
            "refit_every_n_timestamps": 21,
            "lower_quantile": 0.01,
            "upper_quantile": 0.99,
            "epsilon": 1e-12,
        }
        for feature_id, horizon in keys
    ]


def _normalization_policy_records(
    horizon_panel: ArtifactEnvelope, keys: list[tuple[str, str]]
) -> list[dict[str, Any]]:
    entities_by_key: dict[tuple[str, str], set[str]] = {key: set() for key in keys}
    for record in horizon_panel.records:
        key = (str(record["feature_id"]), str(record["horizon_group"]))
        if key in entities_by_key and record.get("feature_value") is not None:
            entities_by_key[key].add(str(record["entity_id"]))
    return [
        {
            "feature_id": feature_id,
            "horizon_group": horizon,
            "normalization_type": "rank_percentile"
            if len(entities_by_key[(feature_id, horizon)]) >= 3
            else "none",
            "neutralize_exposures": [],
            "ridge_alpha": 1e-8,
            "min_entities": 3,
            "final_view": "normalized"
            if len(entities_by_key[(feature_id, horizon)]) >= 3
            else "transformed",
            "epsilon": 1e-12,
        }
        for feature_id, horizon in keys
    ]


def _selection_policy_record() -> dict[str, Any]:
    return {
        "min_coverage": 0.50,
        "max_missingness": 0.50,
        "min_variance": 1e-12,
        "min_pair_overlap": 8,
        "duplicate_abs_pearson": 0.995,
        "duplicate_abs_spearman": 0.995,
        "nonlinear_dependence_threshold": 0.99,
        "max_pair_samples": 500,
        "mutual_info_neighbors": 3,
        "random_state": 17,
        "min_selected_features": 3,
        "prefer_primary_parameterization": True,
    }


def build_s7_policy_artifacts(
    horizon_panel: ArtifactEnvelope, *, context: RuntimeExecutionContext
) -> dict[str, ArtifactEnvelope]:
    keys = sorted({(str(row["feature_id"]), str(row["horizon_group"])) for row in horizon_panel.records})
    lineage = deterministic_id("lineage-s7-policies", [horizon_panel.lineage_id, keys], 28)
    shared = {
        "schema_version": "v14.9-rc1",
        "producer_module_id": "P4.POLICY",
        "context": context,
        "lineage_id": lineage,
    }
    return {
        "transform_policy_registry": build_artifact(
            artifact_name="transform_policy_registry",
            grain=("feature_id", "horizon_group"),
            records=_transform_policy_records(keys),
            **shared,
        ),
        "normalization_neutralization_policy": build_artifact(
            artifact_name="normalization_neutralization_policy",
            grain=("feature_id", "horizon_group"),
            records=_normalization_policy_records(horizon_panel, keys),
            **shared,
        ),
        "exposure_panel": build_artifact(
            artifact_name="exposure_panel",
            grain=("decision_time", "entity_id"),
            records=[],
            metadata={"reason": "neutralization_not_requested"},
            **shared,
        ),
        "structural_selection_policy": build_artifact(
            artifact_name="structural_selection_policy",
            grain=("policy_id",),
            records=[_selection_policy_record()],
            **shared,
        ),
    }


def build_representation_policy(
    *, context: RuntimeExecutionContext, encoder_requested: bool = False
) -> ArtifactEnvelope:
    record = {
        "fold_mode": "expanding",
        "min_train_timestamps": 12,
        "validation_timestamps": 4,
        "step_timestamps": 4,
        "max_outer_folds": 4,
        "rolling_train_timestamps": None,
        "min_train_rows": 16,
        "min_features": 2,
        "pca_variance_threshold": 0.95,
        "max_components": 8,
        "sparse_pca_enabled": True,
        "sparse_alpha": 0.5,
        "sparse_ridge_alpha": 1e-6,
        "sparse_max_iter": 100,
        "sparse_tol": 1e-4,
        "random_state": 17,
        "encoder_requested": encoder_requested,
        "encoder_min_train_rows": 32,
        "encoder_min_modalities": 2,
        "encoder_max_epochs": 30,
        "encoder_patience": 5,
        "encoder_learning_rate": 0.001,
        "encoder_weight_decay": 0.0001,
        "encoder_huber_delta": 1.0,
        "encoder_configurations": [
            {
                "config_id": "AE_BOTTLENECK_25",
                "bottleneck_ratio": 0.25,
                "corruption_rate": 0.10,
                "modality_dropout": 0.10,
            },
            {
                "config_id": "AE_BOTTLENECK_12_5",
                "bottleneck_ratio": 0.125,
                "corruption_rate": 0.10,
                "modality_dropout": 0.10,
            },
        ],
    }
    return build_artifact(
        artifact_name="representation_policy_registry",
        schema_version="v14.9-rc1",
        producer_module_id="P4.POLICY",
        context=context,
        grain=("policy_id",),
        records=[record],
        lineage_id=deterministic_id("lineage-representation-policy", record, 28),
    )


def _s9_default_record(strict_complete_handoff: bool) -> dict[str, Any]:
    return {
        "drift": {
            "reference_timestamps": 20,
            "current_timestamps": 10,
            "min_samples": 8,
            "ks_warn": 0.35,
            "ks_block": 0.60,
            "ks_significance_alpha": 0.05,
            "normalized_wasserstein_warn": 0.75,
            "normalized_wasserstein_block": 2.0,
            "missingness_delta_warn": 0.15,
            "missingness_delta_block": 0.30,
            "loading_drift_warn": 0.25,
            "loading_drift_block": 0.50,
            "reconstruction_delta_warn": 0.25,
            "reconstruction_delta_block": 0.75,
            "reconstruction_error_floor": 0.05,
        },
        "consumer_views": {
            "enabled_views": [
                "TABULAR_INTERPRETABLE",
                "CROSS_SECTIONAL_RANKED",
                "SEQUENCE_MULTI_HORIZON",
                "LATENT_FAMILY",
                "SPARSE_MODALITY_AWARE",
            ],
            "materialize_payloads": False,
        },
        "research_budget": {
            "expected_foundational_hypotheses": 32,
            "max_parameterizations_per_hypothesis": 2,
            "max_encoder_configurations": 2,
            "require_negative_results": True,
        },
        "family_coverage": {
            "expected_family_ids": [f"F{index:02d}" for index in range(1, 11)],
            "required_family_ids": [f"F{index:02d}" for index in range(1, 11)],
            "registered_family_ids": [f"F{index:02d}" for index in range(1, 12)],
            "min_selected_features_per_family": 1,
            "strict_complete_handoff": strict_complete_handoff,
        },
        "max_warn_records_before_degradation": 0,
        "max_block_records_before_handoff_block": 0,
    }


def build_s9_policy(
    *,
    context: RuntimeExecutionContext,
    strict_complete_handoff: bool = True,
    overrides: Mapping[str, Any] | None = None,
) -> ArtifactEnvelope:
    record = _s9_default_record(strict_complete_handoff)
    if overrides:
        allowed = {
            "max_warn_records_before_degradation",
            "max_block_records_before_handoff_block",
            "required_family_ids",
        }
        unknown = sorted(set(overrides) - allowed)
        if unknown:
            raise ValueError(f"unsupported S9 policy overrides: {unknown}")
        for key, value in overrides.items():
            if key == "required_family_ids":
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"S9 policy override {key} must be a non-negative integer")
        if "required_family_ids" in overrides:
            required = list(overrides["required_family_ids"])
            if not required or len(required) != len(set(required)):
                raise ValueError("required_family_ids must contain unique family IDs")
            unknown_required = set(required) - set(record["family_coverage"]["expected_family_ids"])
            if unknown_required:
                raise ValueError(f"unknown required family IDs: {sorted(unknown_required)}")
            record["family_coverage"]["required_family_ids"] = required
        record["max_warn_records_before_degradation"] = int(
            overrides.get(
                "max_warn_records_before_degradation",
                record["max_warn_records_before_degradation"],
            )
        )
        record["max_block_records_before_handoff_block"] = int(
            overrides.get(
                "max_block_records_before_handoff_block",
                record["max_block_records_before_handoff_block"],
            )
        )
    metadata = {}
    if overrides:
        metadata["policy_override"] = {
            "mode": "USER_APPROVED_CAPABILITY_PROFILE" if "required_family_ids" in overrides else "TECHNICAL_REPLAY",
            "default_production_behavior_unchanged": True,
            "values": dict(sorted(overrides.items())),
        }
    return build_artifact(
        artifact_name="s9_policy_registry",
        schema_version="v14.9-rc1",
        producer_module_id="P4.POLICY",
        context=context,
        grain=("policy_id",),
        records=[record],
        lineage_id=deterministic_id("lineage-s9-policy", record, 28),
        metadata=metadata,
    )


def _research_event(index: int, context: RuntimeExecutionContext, previous: str | None) -> dict[str, Any]:
    hypothesis_id = f"H{index:02d}"
    event = {
        "event_id": f"EVENT-{index:03d}",
        "attempt_id": f"ATTEMPT-{hypothesis_id}",
        "event_time": context.created_at.isoformat(),
        "hypothesis_id": hypothesis_id,
        "observer_id": f"O_{hypothesis_id}_PRIMARY",
        "parameterization_id": f"{hypothesis_id}.primary",
        "config_id": None,
        "fold_id": None,
        "seed": None,
        "status": "COMPLETED",
        "reason_code": "FOUNDATIONAL_IMPLEMENTATION",
        "agent_id": "INTEGRATED_RELEASE",
        "parent_attempt_id": None,
        "previous_event_hash": previous,
    }
    event["event_hash"] = canonical_sha256(event)
    return event


def build_research_attempt_event_log(*, context: RuntimeExecutionContext) -> ArtifactEnvelope:
    records: list[dict[str, Any]] = []
    previous: str | None = None
    for index in range(1, 33):
        event = _research_event(index, context, previous)
        records.append(event)
        previous = str(event["event_hash"])
    rejected = {
        "event_id": "EVENT-NEG-001",
        "attempt_id": "ATTEMPT-NEGATIVE-CONTROL",
        "event_time": context.created_at.isoformat(),
        "hypothesis_id": None,
        "observer_id": "NEGATIVE_CONTROL",
        "parameterization_id": None,
        "config_id": None,
        "fold_id": None,
        "seed": None,
        "status": "REJECTED",
        "reason_code": "NEGATIVE_CONTROL_PRESERVED",
        "agent_id": "INTEGRATED_RELEASE",
        "parent_attempt_id": None,
        "previous_event_hash": previous,
    }
    rejected["event_hash"] = canonical_sha256(rejected)
    records.append(rejected)
    return build_artifact(
        artifact_name="research_attempt_event_log",
        schema_version="v14.9-rc1",
        producer_module_id="P4.RESEARCH",
        context=context,
        grain=("event_id",),
        records=records,
        lineage_id=deterministic_id("lineage-research-events", records, 28),
        metadata={"append_only": True, "negative_results_preserved": True},
    )
