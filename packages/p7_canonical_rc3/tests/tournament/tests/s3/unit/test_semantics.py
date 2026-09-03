from __future__ import annotations

import pytest

from quant_pipeline.phase_07_strategy_tournament.tournament.domain.errors import ContractViolation, TemporalViolation
from quant_pipeline.phase_07_strategy_tournament.tournament.modules.P7_S3_M01_candidate_metric_semantics_compiler import run_module

from tests.tournament.tests.s3.factories import UnitConversionPolicy, execution_config, make_bundle


def test_compiles_directed_metrics_and_preserves_raw_values(valid_bundle, config):
    result = run_module(valid_bundle, config)
    records = result["outputs"]["comparable_candidate_metric_panel"]["records"]
    by_key = {(row["candidate_id"], row["metric_id"]): row for row in records}
    assert by_key[("A", "expected_net_payoff")]["raw_value"] == 12.0
    assert by_key[("A", "expected_net_payoff")]["directed_value"] == 12.0
    assert by_key[("A", "expected_shortfall")]["raw_value"] == 5.0
    assert by_key[("A", "expected_shortfall")]["directed_value"] == -5.0


def test_declared_unit_conversion_is_applied():
    conversion = UnitConversionPolicy(
        metric_id="liquidity_quality",
        from_units="percent",
        to_units="normalized_score",
        factor=0.01,
        offset=0.0,
    )
    bundle = make_bundle(
        unit_override=("A", "liquidity_quality", "percent"),
        unit_conversions=(conversion,),
        value_overrides={("A", "liquidity_quality"): 80.0},
    )
    result = run_module(bundle, execution_config())
    row = next(
        row for row in result["outputs"]["comparable_candidate_metric_panel"]["records"]
        if row["candidate_id"] == "A" and row["metric_id"] == "liquidity_quality"
    )
    assert row["raw_value"] == 80.0
    assert row["canonical_value"] == pytest.approx(0.8)

def test_undeclared_unit_conversion_fails_closed():
    bundle = make_bundle(unit_override=("A", "liquidity_quality", "percent"))
    with pytest.raises(ContractViolation) as exc_info:
        run_module(bundle, execution_config())
    assert exc_info.value.code == "P7_S3_UNIT_CONVERSION_NOT_DECLARED"


def test_missing_required_metric_becomes_explicit_block():
    bundle = make_bundle(missing_metric=("B", "expected_shortfall"))
    result = run_module(bundle, execution_config())
    records = result["outputs"]["comparable_candidate_metric_panel"]["records"]
    row = next(row for row in records if row["candidate_id"] == "B" and row["metric_id"] == "expected_shortfall")
    assert row["comparison_status"] == "BLOCKED"
    assert row["raw_value"] is None
    assert row["reason_code"] == "P7_S3_REQUIRED_METRIC_MISSING"


def test_recursive_forbidden_field_scan_rejects_nested_outcome(valid_bundle, config):
    valid_bundle["eligible_strategy_candidate_panel"]["records"][0]["factor_values"]["future_return"] = 99.0
    relaxed = dict(config)
    relaxed["strict_hash_validation"] = False
    with pytest.raises(TemporalViolation) as exc_info:
        run_module(valid_bundle, relaxed)
    assert exc_info.value.code == "P7_S3_FORBIDDEN_FIELD_DETECTED"
