from __future__ import annotations

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_07_strategy_tournament.learning.domain.errors import P7LearningError
from quant_pipeline.phase_07_strategy_tournament.learning.subphases.s6_runtime_scoring.calibration import (
    _confidence_unavailable,
    _confidence_values,
)
from quant_pipeline.phase_07_strategy_tournament.learning.subphases.s6_runtime_scoring.compatibility import (
    _qualification_by_hash,
    _verify_model_hash,
)
from quant_pipeline.phase_07_strategy_tournament.learning.subphases.s6_runtime_scoring.contracts import (
    CandidateFeatureRecord,
    ConfidencePolicy,
    RuntimePolicy,
)


def _candidate(*, data_quality=0.8, ood=0.2) -> CandidateFeatureRecord:
    return CandidateFeatureRecord(
        candidate_id="c", comparison_group_id="g", underlying_id="ABC", horizon="1D",
        objective_family="DIRECTIONAL_UP", capital_at_risk_bucket="LOW",
        feature_schema_hash="a" * 64, feature_available_at="2026-01-01T00:00:00Z",
        feature_values={"x": 1.0}, data_quality_score=data_quality, ood_score=ood,
        lineage_id="lin",
    )


def _policy(**updates) -> ConfidencePolicy:
    values = {
        "policy_version": "v", "min_calibration_queries": 10, "max_fold_ndcg_std": 0.2,
        "minimum_hybrid_confidence": 0.5, "minimum_component_coverage": 0.5,
    }
    values.update(updates)
    return ConfidencePolicy(**values)


def test_minimum_component_coverage_is_effective() -> None:
    candidate = _candidate(data_quality=None, ood=None)
    report = {"calibration_summary": {"query_count": 10}, "fold_ndcg_std": 0.1}
    _, overall, missing, reasons, coverage = _confidence_values(candidate, report, _policy())
    assert coverage == 0.5
    assert overall == pytest.approx(0.5)
    assert set(missing) == {"data_quality", "ood"}
    assert "component_coverage" not in reasons


def test_coverage_below_policy_blocks_confidence_with_reason() -> None:
    candidate = _candidate(data_quality=None, ood=None)
    report = {"calibration_summary": {"query_count": 10}, "fold_ndcg_std": 0.1}
    _, overall, _, reasons, coverage = _confidence_values(
        candidate, report, _policy(minimum_component_coverage=0.75)
    )
    assert coverage == 0.5
    assert overall is None
    assert reasons["component_coverage"] == "P7_CONFIDENCE_COMPONENT_COVERAGE_INSUFFICIENT"


def test_unavailable_confidence_telemetry_comes_from_policy() -> None:
    policy = _policy(required_components=("data_quality", "ood"), minimum_component_coverage=1.0)
    row = _confidence_unavailable(_candidate(), policy)
    assert row["required_components"] == ["data_quality", "ood"]
    assert row["component_coverage"] == 1.0
    assert row["missing_components"] == []


def test_missing_model_hash_has_specific_failure() -> None:
    with pytest.raises(P7LearningError) as exc:
        _verify_model_hash({"serialization_format": "DECLARATIVE_JSON"})
    assert exc.value.issue.code == "P7_LTR_RUNTIME_MODEL_HASH_MISSING"


def test_missing_qualification_hash_is_rejected() -> None:
    with pytest.raises(P7LearningError) as exc:
        _qualification_by_hash(({"qualification_status": "CHAMPION"},))
    assert exc.value.issue.code == "P7_LTR_QUALIFICATION_REGISTRY_INVALID"


def test_runtime_scope_mode_is_explicitly_global_batch() -> None:
    base = dict(
        requested_mode="HYBRID", fallback_mode="INTERPRETABLE_ONLY",
        allowed_implementation_ids=("x",), required_target_id="t",
        required_target_policy_version="v", required_interpretable_scale_id="s",
        min_training_lag_seconds=0,
    )
    assert RuntimePolicy(**base).scope_mode == "GLOBAL_BATCH"
    with pytest.raises(ValidationError):
        RuntimePolicy(**base, scope_mode="PARTITIONED")
