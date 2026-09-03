from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from quant_pipeline.phase_05_underlying_forecasts.domain.distributions import (
    EmpiricalDistribution,
    ParametricDistribution,
    PointDistribution,
    QuantileDistribution,
    QuantilePoint,
    ScenarioDistribution,
    ScenarioPoint,
    point_value,
    quantile_value,
)
from quant_pipeline.phase_05_underlying_forecasts.errors import ContractError, DataQualityError
from quant_pipeline.phase_05_underlying_forecasts.services.identifiers import as_utc, horizon_delta, iso_utc
from quant_pipeline.phase_05_underlying_forecasts.boundary import (
    build_boundary_catalog,
    materialize_consumer_views,
)
from quant_pipeline.phase_05_underlying_forecasts.services.p4_boundary import normalize_conflicts
from quant_pipeline.phase_05_underlying_forecasts.services.risk import (
    bootstrap_scenarios,
    compressed_scenarios,
    evt_tail,
    implied_blend,
    path_risk,
    validate_distribution_set,
)

from .fixtures import build_fixture


def test_identifier_duration_and_timezone_guards():
    assert horizon_delta("2H") == timedelta(hours=2)
    assert horizon_delta("2W") == timedelta(weeks=2)
    assert horizon_delta("2M") == timedelta(days=60)
    assert iso_utc("2025-01-01T00:00:00Z").endswith("Z")
    with pytest.raises(DataQualityError):
        horizon_delta("0D")
    with pytest.raises(ValueError):
        as_utc(datetime(2025, 1, 1))


def _catalog(fixture, **overrides):
    values = {
        "handoff": fixture["phase5_feature_handoff_manifest"],
        "view_manifest": fixture["model_consumer_view_manifest"],
        "view_bundle": fixture["model_consumer_view_bundle"],
        "quality_gate": fixture["p4_quality_gate_decision"],
        "artifact_catalog": fixture["p4_artifact_catalog"],
        "expected_cycle_id": "cycle-001",
        "p5_as_of_time": fixture["as_of_time"],
        "p5_generated_at": fixture["generated_at"],
    }
    values.update(overrides)
    return build_boundary_catalog(**values)


def test_p4_v149_boundary_accepts_reference_only_native_handoff():
    fixture = build_fixture()
    catalog = _catalog(fixture)
    views, compatibility = materialize_consumer_views(catalog)
    assert {row["view_id"] for row in views} == {
        "TABULAR_INTERPRETABLE", "CROSS_SECTIONAL_RANKED",
        "SEQUENCE_MULTI_HORIZON", "LATENT_FAMILY", "SPARSE_MODALITY_AWARE",
    }
    assert all(row["authorized"] for row in compatibility)
    assert all(row["horizon_preserved"] for row in views)


def test_p4_v149_boundary_rejects_hash_mutation():
    fixture = build_fixture()
    handoff = deepcopy(fixture["phase5_feature_handoff_manifest"])
    handoff["records"][0]["record_count"] += 1
    with pytest.raises(ContractError, match="content_hash mismatch"):
        _catalog(fixture, handoff=handoff)


def test_p4_v149_boundary_rejects_cycle_and_future_clocks():
    fixture = build_fixture()
    with pytest.raises(ContractError, match="cycle_id differs"):
        _catalog(fixture, expected_cycle_id="other-cycle")
    with pytest.raises(ContractError, match="as_of_time exceeds"):
        _catalog(fixture, p5_as_of_time=fixture["as_of_time"] - timedelta(seconds=1))


def test_p4_v149_boundary_rejects_reference_mismatch():
    fixture = build_fixture()
    bundle = deepcopy(fixture["model_consumer_view_bundle"])
    bundle["records"][0]["artifact_references"][0]["content_hash"] = "0" * 64
    # Re-hash the envelope so the failure is specifically at the cross-reference layer.
    from quant_pipeline.phase_05_underlying_forecasts.boundary import canonical_sha256
    bundle["content_hash"] = canonical_sha256({
        "records": bundle["records"], "metadata": bundle["metadata"], "alias_of": bundle["alias_of"]
    })
    with pytest.raises(ContractError, match="reference .*content_hash mismatch"):
        _catalog(fixture, view_bundle=bundle)


def test_p4_v149_conflict_normalization_preserves_grain_and_bounds():
    fixture = build_fixture()
    normalized = normalize_conflicts(fixture["perspective_conflict_panel"])
    assert len(normalized) == 3
    assert all(row["horizon_group"] == "SHORT" for row in normalized)
    invalid = deepcopy(fixture["perspective_conflict_panel"])
    invalid["records"][0]["conflict_score"] = 1.1
    with pytest.raises(DataQualityError, match="between zero and one"):
        normalize_conflicts(invalid)


def test_distribution_value_paths_and_guards():
    point = PointDistribution(value=2.0)
    quantiles = QuantileDistribution(quantiles=(QuantilePoint(level=0.1, value=-1.0), QuantilePoint(level=0.9, value=1.0)))
    normal = ParametricDistribution(family="NORMAL", location=0.0, scale=1.0)
    student = ParametricDistribution(family="STUDENT_T", location=0.0, scale=1.0, degrees_of_freedom=5.0)
    empirical = EmpiricalDistribution(samples=(-2.0, 0.0, 4.0))
    scenarios = ScenarioDistribution(scenarios=(
        ScenarioPoint(scenario_id="low", value=-1.0, probability=0.4),
        ScenarioPoint(scenario_id="high", value=2.0, probability=0.6),
    ))
    assert point_value(point) == 2.0
    assert point_value(quantiles) == pytest.approx(0.0)
    assert point_value(normal) == 0.0
    assert point_value(empirical) == 0.0
    assert point_value(scenarios) == pytest.approx(0.8)
    assert quantile_value(normal, 0.5) == pytest.approx(0.0)
    assert np.isfinite(quantile_value(student, 0.95))
    assert quantile_value(empirical, 0.5) == 0.0
    assert quantile_value(scenarios, 0.2) == -1.0
    assert quantile_value(scenarios, 0.99) == 2.0
    with pytest.raises(ValueError, match="between zero and one"):
        quantile_value(point, 1.0)
    with pytest.raises(ValueError, match="degrees_of_freedom"):
        ParametricDistribution(family="STUDENT_T", location=0.0, scale=1.0)
    with pytest.raises(ValueError, match="must not declare"):
        ParametricDistribution(family="NORMAL", location=0.0, scale=1.0, degrees_of_freedom=5.0)


def test_risk_fallback_liquidity_and_validation_failures():
    positive = np.full(40, 0.01)
    tail = evt_tail(positive)
    assert tail["method"] == "EMPIRICAL_POSITIVE_LOSS_FALLBACK"
    metrics = path_risk(np.asarray([0.01, -0.02, 0.03, -0.01, 0.0, 0.02, -0.03, 0.01]), np.arange(8) / 100)
    assert metrics["liquidity_risk"] > 0.0
    with pytest.raises(DataQualityError, match="positive finite IV"):
        implied_blend(0.01, {"implied_volatility": 0.0, "coverage": 0.8})
    with pytest.raises(DataQualityError, match="coverage"):
        implied_blend(0.01, {"implied_volatility": 0.2, "coverage": 2.0})
    with pytest.raises(DataQualityError, match="count and block"):
        bootstrap_scenarios(np.linspace(-0.02, 0.02, 12), seed=1, count=1, block=5)
    compressed = compressed_scenarios(EmpiricalDistribution(samples=tuple(np.linspace(-0.1, 0.1, 20))))
    assert sum(row.probability for row in compressed.scenarios) == pytest.approx(1.0)
    report = validate_distribution_set([
        {"record_id": "a", "resolver_id": "r", "underlying": "AAA", "target_id": "x", "horizon": "1D", "unit": "positive_loss", "distribution": {"kind": "POINT", "value": -1.0}},
        {"record_id": "b", "resolver_id": "r", "underlying": "AAA", "target_id": "x", "horizon": "1D", "unit": "positive_loss", "distribution": {"kind": "POINT", "value": 1.0}},
    ])
    assert not report["passed"]
    with pytest.raises(DataQualityError, match="requires records"):
        validate_distribution_set([])
