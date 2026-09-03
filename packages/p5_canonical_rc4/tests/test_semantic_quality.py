from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from quant_pipeline.phase_05_underlying_forecasts.domain.distributions import (
    PointDistribution,
    quantile_value,
)
from quant_pipeline.phase_05_underlying_forecasts.domain.forecast import (
    ForecastMemberPanel,
    ForecastMemberRecord,
)
from quant_pipeline.phase_05_underlying_forecasts.services.dependence import validate_covariance
from quant_pipeline.phase_05_underlying_forecasts.services.ensemble import build_ensemble
from quant_pipeline.phase_05_underlying_forecasts.services.risk import (
    compressed_scenarios,
    empirical_quantiles,
    evt_tail,
)


def _member(identifier: str, value: float, family: str) -> ForecastMemberRecord:
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return ForecastMemberRecord(
        record_id=identifier,
        as_of_time=now,
        prediction_timestamp=now + timedelta(days=1),
        underlying="AAA",
        target_id="excess_return_1d",
        horizon="1D",
        unit="decimal_return",
        resolver_id=identifier,
        resolver_family=family,
        model_artifact_id=f"model-{identifier}",
        feature_view_id="TABULAR_INTERPRETABLE",
        training_cutoff=now - timedelta(days=1),
        lineage_id=f"lineage-{identifier}",
        distribution=PointDistribution(value=value),
    )


def test_signed_return_quantiles_remain_signed():
    values = np.asarray([-0.08, -0.05, -0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03, 0.04])
    distribution = empirical_quantiles(values)
    assert quantile_value(distribution, 0.05) < 0.0
    assert quantile_value(distribution, 0.50) < 0.01


def test_evt_outputs_positive_loss_and_ordered_tail_metrics():
    generator = np.random.default_rng(7)
    values = generator.standard_t(df=4, size=600) * 0.012
    tail = evt_tail(values)
    assert tail["var"] > 0.0
    assert tail["expected_shortfall"] >= tail["var"]
    assert tail["threshold"] > 0.0


def test_scenario_probabilities_sum_to_one():
    empirical = type("Empirical", (), {"samples": tuple(np.linspace(-0.05, 0.05, 64))})()
    scenario = compressed_scenarios(empirical)
    assert abs(sum(row.probability for row in scenario.scenarios) - 1.0) < 1e-12


def test_covariance_validation_repairs_to_psd():
    matrix = np.asarray([[1.0, 2.0], [2.0, 1.0]])
    repaired, diagnostics = validate_covariance(matrix, repair=True)
    assert np.allclose(repaired, repaired.T)
    assert float(np.min(np.linalg.eigvalsh(repaired))) >= -1e-10
    assert diagnostics["repair_applied"] is True


def test_ensemble_preserves_member_disagreement_in_distribution():
    panel = ForecastMemberPanel(records=(
        _member("negative", -0.02, "LINEAR"),
        _member("positive", 0.03, "TREE"),
    ))
    candidates = {"selected_record_ids": ["negative", "positive"]}
    scoring = {"records": [
        {"resolver_id": "negative", "target_id": "excess_return_1d", "horizon": "1D", "unit": "decimal_return", "status": "OK", "mse": 1.0, "sample_size": 20, "coverage_90": 0.9, "pit_ks_pvalue": 0.1},
        {"resolver_id": "positive", "target_id": "excess_return_1d", "horizon": "1D", "unit": "decimal_return", "status": "OK", "mse": 1.0, "sample_size": 20, "coverage_90": 0.9, "pit_ks_pvalue": 0.1},
    ]}
    context = {"records": [{
        "underlying": "AAA", "target_id": "excess_return_1d", "horizon": "1D", "unit": "decimal_return",
        "context_uncertainty": 0.2, "context_components": {"ood": 0.1, "regime_uncertainty": 0.2},
        "recommended_action": "USE",
    }]}
    output, _, _ = build_ensemble(panel, candidates, scoring, context, confidence_floor=0.0)
    record = output.records[0]
    assert record.epistemic_uncertainty > 0.0
    assert quantile_value(record.distribution, 0.05) < quantile_value(record.distribution, 0.95)
