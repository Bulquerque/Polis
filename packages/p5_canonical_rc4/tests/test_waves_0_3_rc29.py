from __future__ import annotations

import copy
from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest
import yaml
from jsonschema import Draft202012Validator

from quant_pipeline.phase_05_underlying_forecasts.domain.distributions import (
    PointDistribution,
    QuantilePoint,
)
from quant_pipeline.phase_05_underlying_forecasts.domain.v2_base import (
    CalibrationStatus,
    CapabilityStatus,
    ScenarioType,
)
from quant_pipeline.phase_05_underlying_forecasts.domain.v2_marginals import (
    MarketFeatureRecord,
    ReturnDistributionRecord,
)
from quant_pipeline.phase_05_underlying_forecasts.domain.v2_scenarios import ScenarioPathRecord
from quant_pipeline.phase_05_underlying_forecasts.errors import DataQualityError, ReasonCode
from quant_pipeline.phase_05_underlying_forecasts.services.marginal_models import (
    conditional_quantiles,
    evt_diagnostics,
    heavy_tail_candidates,
)
from quant_pipeline.phase_05_underlying_forecasts.services.model_bindings import MODEL_BINDINGS
from quant_pipeline.phase_05_underlying_forecasts.services.tabular import feature_rows, target_rows
from quant_pipeline.phase_05_underlying_forecasts.services.targets import build_target_registry
from quant_pipeline.phase_05_underlying_forecasts.services.temporal_evaluation import build_evaluation_plan
from quant_pipeline.phase_05_underlying_forecasts.subphases import s2

from .fixtures import build_fixture

ROOT = Path(__file__).resolve().parents[1]


def test_wave0_schema_registry_contains_all_central_v2_contracts() -> None:
    registry = yaml.safe_load((ROOT / "SCHEMA_REGISTRY.yaml").read_text(encoding="utf-8"))
    identifiers = {row["schema_id"] for row in registry["schemas"]}
    required = {
        "MarketFeatureBundle", "ReturnDistributionPanel", "VolatilityDistributionPanel",
        "PathRiskForecastPanel", "ScenarioPathPanel", "AmbiguitySet", "DependenceState",
        "RegimeOODState", "ForecastConfidence", "Phase6StrategyScenarioManifest",
    }
    assert required <= identifiers
    for name in required:
        schema = __import__("json").loads((ROOT / "schemas" / f"{name}.schema.json").read_text())
        Draft202012Validator.check_schema(schema)


def test_wave0_contracts_fail_closed_on_clocks_probabilities_and_stress_mass() -> None:
    fixture = build_fixture()
    decision = fixture["as_of_time"]
    with pytest.raises(ValueError, match="available_at cannot exceed decision_time"):
        MarketFeatureRecord(
            underlying="AAA", decision_time=decision, available_at=decision + timedelta(seconds=1),
            feature_view_id="TABULAR_INTERPRETABLE", view_type="TABULAR_INTERPRETABLE",
            feature_schema_version="2.0.0", feature_values={"x": 1.0}, quality_state="PASS",
            horizon_group="SHORT", representation_type="TABULAR", artifact_id="a",
            artifact_sha256="0" * 64, lineage_id="lineage",
        )
    with pytest.raises(ValueError, match="must sum to one"):
        ReturnDistributionRecord(
            underlying="AAA", decision_time=decision, horizon="1D", target_id="RETURN",
            distribution_version="2.0.0", mean=0.0, median=0.0,
            quantiles=(
                QuantilePoint(level=0.05, value=-1.0), QuantilePoint(level=0.50, value=0.0),
                QuantilePoint(level=0.95, value=1.0),
            ),
            probability_positive=0.8, probability_negative=0.3,
            distribution_family="POINT", support=(None, None), units="decimal_return",
            model_member_ids=("m",), calibration_status=CalibrationStatus.UNCALIBRATED,
            confidence=0.5, distribution=PointDistribution(value=0.0), lineage_id="lineage",
        )
    with pytest.raises(ValueError, match="cannot claim statistical probability"):
        ScenarioPathRecord(
            underlying="AAA", decision_time=decision, horizon="1D", scenario_id="stress",
            scenario_type=ScenarioType.STRESS, probability=0.1, path_step=1,
            path_timestamp=decision + timedelta(days=1), future_return=-0.2,
            seed=1, generator_id="stress-v1", lineage_id="lineage",
        )


def test_wave0_reason_registry_matches_runtime_enum() -> None:
    registry = yaml.safe_load((ROOT / "REASON_CODE_REGISTRY.yaml").read_text(encoding="utf-8"))
    assert {row["code"] for row in registry["reason_codes"]} == {item.value for item in ReasonCode}


def test_wave1_missing_feature_availability_is_rejected() -> None:
    view = {
        "records": [{
            "underlying": "AAA", "decision_time": "2025-01-02T00:00:00+00:00",
            "horizon_group": "SHORT", "features": {"x": 1.0}, "lineage_id": "lineage",
        }]
    }
    with pytest.raises(DataQualityError, match="explicit available_at"):
        feature_rows(view)


def test_wave2_target_registry_declares_full_scope_with_explicit_capability() -> None:
    registry = build_target_registry((("custom_return", "5D", "decimal_return"),))
    canonical = {row.target_id for row in registry if row.target_id != "custom_return"}
    assert len(canonical) == 17
    custom = next(row for row in registry if row.target_id == "custom_return")
    assert custom.horizon == "5D"
    assert custom.availability_status is CapabilityStatus.AVAILABLE
    assert any(row.availability_status is CapabilityStatus.UNAVAILABLE for row in registry)


@pytest.mark.parametrize("window_type", ["EXPANDING", "ROLLING", "ANCHORED"])
def test_wave2_multifold_plan_is_target_specific_and_test_sealed(window_type: str) -> None:
    fixture = build_fixture()
    records = target_rows(
        fixture["p5_offline_training_outcome_bundle"], training_cutoff=fixture["as_of_time"]
    )
    plan, receipt = build_evaluation_plan(records, window_type=window_type)
    assert receipt["fold_count"] >= 2
    assert plan["sealed_holdout"] == "TEST"
    assert plan["target_specific"] is True
    folds = plan["target_plans"][0]["folds"]
    test_partitions = []
    for fold in folds:
        parts = {row["name"]: row["timestamps"] for row in fold["partitions"]}
        assert max(parts["TRAIN"]) < min(parts["VALIDATION"])
        assert max(parts["VALIDATION"]) < min(parts["CALIBRATION"])
        assert max(parts["CALIBRATION"]) < min(parts["TEST"])
        test_partitions.append(parts["TEST"])
    assert all(partition == test_partitions[0] for partition in test_partitions)


def test_wave2_future_outcome_is_excluded_from_economic_training_records() -> None:
    fixture = build_fixture()
    base = s2.m01(
        {"p5_offline_training_outcome_bundle": fixture["p5_offline_training_outcome_bundle"]},
        as_of_time=fixture["as_of_time"],
    )
    changed_bundle = copy.deepcopy(fixture["p5_offline_training_outcome_bundle"])
    future = copy.deepcopy(changed_bundle["records"][-1])
    future_time = fixture["as_of_time"] + timedelta(days=30)
    future.update({
        "prediction_timestamp": future_time.isoformat(),
        "label_end_time": (future_time + timedelta(days=1)).isoformat(),
        "available_at": (future_time + timedelta(days=1)).isoformat(),
        "lineage_id": "future-lineage",
    })
    changed_bundle["records"].append(future)
    changed = s2.m01(
        {"p5_offline_training_outcome_bundle": changed_bundle}, as_of_time=fixture["as_of_time"]
    )
    assert base.values[0] == changed.values[0]
    assert changed.diagnostics["excluded_future_outcomes"] == base.diagnostics["excluded_future_outcomes"] + 1


def test_wave2_model_bindings_are_declarative_bounded_and_cpu_first() -> None:
    families = {row.resolver_family for row in MODEL_BINDINGS if row.capability_status is CapabilityStatus.AVAILABLE}
    assert {"BASELINE", "LINEAR", "ROBUST_LINEAR", "STATE_SPACE", "TREE", "KERNEL"} <= families
    for row in MODEL_BINDINGS:
        assert row.resource_budget["max_seconds"] > 0
        assert row.resource_budget["max_memory_mb"] > 0
    assert all(row.capability_status is not CapabilityStatus.AVAILABLE for row in MODEL_BINDINGS if row.resolver_family in {"TEMPORAL_NEURAL", "FOUNDATION"})


def test_wave3_quantiles_heavy_tails_and_evt_are_rich_and_deterministic() -> None:
    generator = np.random.default_rng(123)
    values = np.concatenate([generator.normal(0.0, 0.01, 100), generator.normal(-0.03, 0.025, 20)])
    distribution, diagnostics = conditional_quantiles(values)
    quantiles = [row.value for row in distribution.quantiles]
    assert quantiles == sorted(quantiles)
    assert diagnostics["non_crossing_enforced"] is True
    candidates = heavy_tail_candidates(values)
    assert {row[0] for row in candidates} == {"student-t", "ged", "two-component-normal-mixture"}
    assert sum(bool(row[2]["selected_by_holdout_score"]) for row in candidates) == 1
    tail = evt_diagnostics(values)
    assert tail["expected_shortfall"] >= tail["var"] >= 0.0
    assert len(tail["var_bootstrap_ci"]) == 2
