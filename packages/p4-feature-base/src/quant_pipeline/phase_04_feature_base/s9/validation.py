from __future__ import annotations

from typing import Any

from .artifacts import ArtifactEnvelope
from .errors import S9Error
from .records import S9Policy

FORBIDDEN_FIELDS = {
    "target",
    "label",
    "future_return",
    "future_volatility",
    "prediction",
    "signal_direction",
    "candidate_id",
    "rank_score",
    "portfolio_weight",
    "realized_pnl",
    "sharpe",
}

REQUIRED_INPUTS = (
    "underlying_feature_matrix_raw",
    "underlying_feature_matrix_selected",
    "underlying_feature_factors_pca",
    "underlying_feature_embeddings",
    "feature_selection_report",
    "feature_transform_state_manifest",
    "causal_transform_fit_state_manifest",
    "normalization_neutralization_fit_state_manifest",
    "feature_diversity_redundancy_report",
    "pca_fit_state_manifest",
    "encoder_fit_state_manifest",
    "representation_quality_report",
    "representation_fold_plan",
    "s9_policy_registry",
    "research_attempt_event_log",
)


def require_artifacts(inputs: dict[str, ArtifactEnvelope], names: tuple[str, ...] = REQUIRED_INPUTS) -> None:
    missing = [name for name in names if name not in inputs]
    if missing:
        raise S9Error("P4_S9_INPUT_INVALID", f"missing artifacts: {missing}")
    selected = [inputs[name] for name in names]
    reference = selected[0]
    for name, artifact in zip(names, selected, strict=True):
        artifact.validate_payload()
        if artifact.artifact_name != name:
            raise S9Error(
                "P4_S9_ARTIFACT_NAME_MISMATCH",
                f"key={name} artifact={artifact.artifact_name}",
            )
        current = (artifact.run_id, artifact.cycle_id, artifact.as_of_time)
        expected = (reference.run_id, reference.cycle_id, reference.as_of_time)
        if current != expected:
            raise S9Error("P4_S9_CYCLE_MISMATCH", f"artifact {name} is from another snapshot")


def reject_forbidden(value: Any, path: str = "root") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in FORBIDDEN_FIELDS:
                raise S9Error("P4_S9_FORBIDDEN_FIELD", f"{path}.{key}")
            reject_forbidden(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            reject_forbidden(child, f"{path}[{index}]")


def parse_policy(artifact: ArtifactEnvelope) -> S9Policy:
    if artifact.record_count != 1:
        raise S9Error("P4_S9_POLICY_INVALID", "S9 policy must contain exactly one record")
    return S9Policy.model_validate(artifact.records[0])
