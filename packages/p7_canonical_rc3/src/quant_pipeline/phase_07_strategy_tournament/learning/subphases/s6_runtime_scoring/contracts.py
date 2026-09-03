from __future__ import annotations
from collections.abc import Mapping
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from ...domain.errors import fail

REQUIRED_TOURNAMENT_ARTIFACTS = (
    "comparison_group_registry", "pareto_candidate_panel", "factor_adjusted_candidate_panel",
    "interpretable_score_panel", "interpretable_score_decomposition_panel",
    "metric_semantics_registry", "candidate_lineage_panel", "tournament_audit_report",
)

class CandidateFeatureRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    candidate_id: str
    comparison_group_id: str
    underlying_id: str
    horizon: str
    objective_family: str
    capital_at_risk_bucket: str
    feature_schema_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    feature_available_at: str
    feature_values: dict[str, float | None]
    data_quality_score: float | None = Field(default=None, ge=0.0, le=1.0)
    ood_score: float | None = Field(default=None, ge=0.0, le=1.0)
    lineage_id: str

    @field_validator("feature_values")
    @classmethod
    def nonempty_features(cls, value: dict[str, float | None]) -> dict[str, float | None]:
        if not value:
            raise ValueError("feature_values cannot be empty")
        return dict(sorted(value.items()))

class InterpretableScoreRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    candidate_id: str
    comparison_group_id: str
    interpretable_score: float
    scale_id: str
    score_status: str

class RuntimePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    requested_mode: str
    fallback_mode: str
    allowed_implementation_ids: tuple[str, ...]
    required_target_id: str
    required_target_policy_version: str
    required_interpretable_scale_id: str
    scope_mode: Literal["GLOBAL_BATCH"] = "GLOBAL_BATCH"
    min_training_lag_seconds: float = Field(ge=0.0)

class ConfidencePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    policy_version: str
    min_calibration_queries: int = Field(ge=1)
    max_fold_ndcg_std: float = Field(gt=0.0)
    minimum_hybrid_confidence: float = Field(ge=0.0, le=1.0)
    required_components: tuple[str, ...] = (
        "calibration_evidence", "fold_stability", "data_quality", "ood"
    )
    minimum_component_coverage: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("required_components")
    @classmethod
    def nonempty_unique_components(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or any(not item for item in value) or len(value) != len(set(value)):
            raise ValueError("required_components must be nonempty and unique")
        supported = {"calibration_evidence", "fold_stability", "data_quality", "ood"}
        unknown = set(value) - supported
        if unknown:
            raise ValueError(f"unsupported confidence components: {sorted(unknown)}")
        return value

class BlendPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    policy_version: str
    interpretable_weight: float = Field(ge=0.0, le=1.0)
    ltr_weight: float = Field(ge=0.0, le=1.0)

    @field_validator("ltr_weight")
    @classmethod
    def weights_close(cls, value: float, info: Any) -> float:
        other = float(info.data.get("interpretable_weight", 0.0))
        if abs(other + value - 1.0) > 1e-12:
            raise ValueError("blend weights must sum to one")
        return value

def artifact_map(manifest_record: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    refs = manifest_record.get("artifact_references")
    if not isinstance(refs, list):
        fail("P7_LTR_TOURNAMENT_HANDOFF_INVALID", "artifact_references must be a list")
    result: dict[str, dict[str, Any]] = {}
    for raw in refs:
        if not isinstance(raw, Mapping) or not isinstance(raw.get("artifact_name"), str):
            fail("P7_LTR_TOURNAMENT_HANDOFF_INVALID", "invalid artifact reference")
        name = str(raw["artifact_name"])
        if name in result:
            fail("P7_LTR_TOURNAMENT_HANDOFF_INVALID", f"duplicate reference {name}")
        result[name] = dict(raw)
    return result
