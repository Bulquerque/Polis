from __future__ import annotations

from datetime import datetime, timedelta, timezone

from quant_pipeline.phase_05_underlying_forecasts.domain.distributions import EmpiricalDistribution, PointDistribution
from quant_pipeline.phase_05_underlying_forecasts.domain.forecast import EnsembleForecastPanel, EnsembleForecastRecord, ForecastMemberPanel, ForecastMemberRecord
from quant_pipeline.phase_05_underlying_forecasts.services.downstream import build_ambiguity_set, build_market_belief_state, handoffs
from quant_pipeline.phase_05_underlying_forecasts.services.ensemble import build_ensemble


def _member(identifier: str, value: float, mse: float) -> tuple[ForecastMemberRecord, dict]:
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    record = ForecastMemberRecord(
        record_id=identifier, as_of_time=now, prediction_timestamp=now + timedelta(days=1),
        underlying="AAA", target_id="return_1d", horizon="1D", unit="decimal_return",
        resolver_id=identifier, resolver_family=identifier.upper(), model_artifact_id=f"m-{identifier}",
        feature_view_id="TABULAR_INTERPRETABLE", training_cutoff=now - timedelta(days=1),
        lineage_id=f"l-{identifier}", distribution=PointDistribution(value=value),
    )
    score = {"resolver_id": identifier, "target_id": "return_1d", "horizon": "1D", "unit": "decimal_return", "status": "OK", "mse": mse, "sample_size": 30, "coverage_90": 0.9, "pit_ks_pvalue": 0.1}
    return record, score


def _ensemble(metadata=None) -> EnsembleForecastPanel:
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    member = _member("a", 0.01, 1.0)[0]
    if metadata:
        member = member.model_copy(update={"metadata": metadata})
    return EnsembleForecastPanel(records=(EnsembleForecastRecord(
        record_id="ensemble-a", as_of_time=now, prediction_timestamp=now + timedelta(days=1),
        underlying="AAA", target_id="return_1d", horizon="1D", unit="decimal_return",
        distribution=EmpiricalDistribution(samples=(-0.1, 0.0, 0.1)), member_ids=(member.record_id,),
        weights=(1.0,), epistemic_uncertainty=0.01, confidence=0.8, lineage_id="ensemble-lineage",
    ),))


def test_wave3_ensemble_uses_out_of_sample_loss_weights():
    first, first_score = _member("first", -0.02, 0.25)
    second, second_score = _member("second", 0.02, 1.0)
    context = {"records": [{
        "underlying": "AAA", "target_id": "return_1d", "horizon": "1D", "unit": "decimal_return",
        "context_uncertainty": 0.2, "context_components": {"ood": 0.1, "regime_uncertainty": 0.2},
        "recommended_action": "USE",
    }]}
    output, _, report = build_ensemble(
        ForecastMemberPanel(records=(first, second)),
        {"selected_record_ids": [first.record_id, second.record_id]},
        {"records": [first_score, second_score]}, context, confidence_floor=0.0,
    )
    assert output.records[0].weights[0] > output.records[0].weights[1]
    assert report["records"][0]["combiner"] == "INVERSE_VALIDATION_LOSS_PROBABILISTIC_MIXTURE"


def test_wave3_ambiguity_probabilities_are_normalized():
    scenarios = {"records": [{"record_id": "ensemble-a", "underlying": "AAA", "target_id": "return_1d", "horizon": "1D", "unit": "decimal_return", "samples": [-0.1, 0.0, 0.1]}]}
    result = build_ambiguity_set(scenarios, _confidence(), _context_panel())
    assert result["availability"] == "AVAILABLE"
    assert all(abs(sum(vector) - 1.0) < 1e-12 for vector in result["records"][0]["alternative_probabilities"])


def test_wave3_never_invents_terminal_price_without_anchor():
    scenarios = {"records": [{"record_id": "ensemble-a", "underlying": "AAA", "target_id": "return_1d", "horizon": "1D", "unit": "decimal_return", "samples": [-0.1, 0.0, 0.1]}]}
    ambiguity = build_ambiguity_set(scenarios, _confidence(), _context_panel())
    belief = build_market_belief_state(
        _ensemble(), scenarios, ambiguity, _context_panel(),
        decision_time="2025-01-01T00:10:00+00:00", confidence_panel=_confidence(),
    )["records"][0]
    assert belief["scenario_capability"] == "LIMITED"
    assert belief["scenarios"] == []


def test_wave3_builds_p6_v2_prices_when_anchor_is_explicit():
    panel = _ensemble({"spot_price": 100.0})
    scenarios = {"records": [{"record_id": "ensemble-a", "underlying": "AAA", "target_id": "return_1d", "horizon": "1D", "unit": "decimal_return", "samples": [-0.1, 0.0, 0.1], "price_anchor": 100.0}]}
    ambiguity = build_ambiguity_set(scenarios, _confidence(), _context_panel())
    belief = build_market_belief_state(
        panel, scenarios, ambiguity, _context_panel(),
        decision_time="2025-01-01T00:10:00+00:00", confidence_panel=_confidence(),
    )["records"][0]
    assert belief["scenario_capability"] == "AVAILABLE"
    assert [row["terminal_underlying_price"] for row in belief["scenarios"]] == [90.0, 100.0, 110.00000000000001]


def test_wave3_handoff_is_content_addressed_and_declares_p7_boundary():
    args = dict(created_at="2025-01-01T00:00:00+00:00", output_references={"forecast_scenario_panel": {"content_hash": "abc"}}, forecast_member_panel={"records": []}, ensemble_selection_report={"records": []}, representation_ablation_report={"records": []})
    first = handoffs(**args)
    second = handoffs(**args)
    assert first[0]["artifact_id"] == second[0]["artifact_id"]
    assert first[0]["content_sha256"] == second[0]["content_sha256"]
    assert first[0]["consumer_views"]["P7"] == "P7_CONSUMES_P6_CANDIDATES_NOT_RAW_P5_FORECASTS"
    assert first[3]["production_promotion_allowed"] is False


def _confidence():
    return {"records": [{
        "record_id": "ensemble-a", "underlying": "AAA", "target_id": "return_1d", "horizon": "1D", "unit": "decimal_return",
        "confidence": 0.8, "overall_confidence": 0.8, "calibration_status": "CALIBRATED", "abstained": False,
    }]}


def _context_panel():
    return {"records": [{
        "underlying": "AAA", "target_id": "return_1d", "horizon": "1D", "unit": "decimal_return",
        "context_uncertainty": 0.2, "dominant_regime": "NORMAL",
    }]}
