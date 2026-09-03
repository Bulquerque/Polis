from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from quant_pipeline.phase_06_strategy_synthesis.boundaries.p5 import parse_p5_handoff
from quant_pipeline.phase_06_strategy_synthesis.boundaries.p5_evidence import (
    availability_map,
    availability_reason,
    lineage_map,
)
from quant_pipeline.phase_06_strategy_synthesis.boundaries.p5_scenarios import (
    _capability_reasons,
    _confidence_components,
    _distribution_samples,
    _normalize_scenario_mass,
    _paths_index,
    _regime_context,
    _scenario_distribution,
    _scenarios_from_distribution,
    _scenarios_from_paths,
    _stratified_values,
)
from quant_pipeline.phase_06_strategy_synthesis.boundaries.p5_utils import (
    as_datetime,
    horizon_days,
    normalized,
    raw_records,
)
from quant_pipeline.phase_06_strategy_synthesis.domain.enums import CapabilityStatus
from quant_pipeline.phase_06_strategy_synthesis.domain.models import (
    BeliefScenario,
    P5ForecastConfidenceRecord,
    P5RegimeOODRecord,
    P5ReturnDistributionRecord,
    P5ScenarioPathRecord,
)
from quant_pipeline.phase_06_strategy_synthesis.foundation.errors import Phase6ContractError
from quant_pipeline.phase_06_strategy_synthesis.foundation.hashing import canonical_sha256

UTC = timezone.utc
DECISION = datetime(2025, 6, 9, 0, 10, tzinfo=UTC)


def test_horizon_and_raw_record_helpers_cover_supported_shapes() -> None:
    assert horizon_days("24H") == 1
    assert horizon_days("2D") == 2
    assert horizon_days("2W") == 14
    assert horizon_days("3M") == 90
    with pytest.raises(ValueError):
        horizon_days("12H")
    with pytest.raises(ValueError):
        horizon_days("bad")

    assert as_datetime(DECISION) is DECISION
    assert normalized("not-a-time") == "not-a-time"
    assert raw_records({"records": [1]}) == [1]
    assert raw_records({"artifact": {"records": [2]}}) == [2]
    assert raw_records({"content": {"records": [3]}}) == [3]
    assert raw_records({}) == []


def test_evidence_helpers_preserve_unavailable_and_lineage() -> None:
    availability = availability_map({"records": [
        {"artifact_type": "a", "availability": "DEGRADED"},
        "ignored",
    ]})
    assert availability == {"a": "DEGRADED"}
    assert availability_map(None) == {}
    assert availability_reason("a", {}, availability) == "P5_DEGRADED"
    assert availability_reason("a", {"reason_code": "DIRECT"}, availability) == "DIRECT"
    assert availability_reason("missing", {}, availability) is None

    lineage = lineage_map({"content": {"artifacts": [
        {"artifact_type": "a", "artifact_id": "id"},
        {"bad": "row"},
    ]}})
    assert lineage["a"]["artifact_id"] == "id"
    assert lineage_map(None) == {}
    assert lineage_map({"content": {}}) == {}


def test_native_p5_artifact_without_manifest_is_rejected() -> None:
    native = {
        "producer_phase": "P5",
        "artifact_sha256": "0" * 64,
        "artifact_id": "belief",
        "content_sha256": canonical_sha256([]),
        "records": [],
    }
    with pytest.raises(Phase6ContractError) as captured:
        parse_p5_handoff({"market_belief_state": native}, DECISION, "P6.S1.M01")
    assert captured.value.reason_code == "P6_P5_MANIFEST_INVALID"


def test_real_v1_shape_is_accepted_without_fabricating_scenarios() -> None:
    records = [{
        "underlying": "AAA",
        "prediction_timestamp": (DECISION - timedelta(minutes=1)).isoformat(),
        "horizon": "5D",
        "confidence": "0.4",
    }]
    artifact = {
        "artifact_id": "p5-v1-real",
        "content_sha256": canonical_sha256(records),
        "records": records,
    }
    parsed = parse_p5_handoff({"underlying_forecast_panel": artifact}, DECISION, "P6.S1.M01")
    belief = parsed.beliefs[0]
    assert belief.horizon_days == 5
    assert belief.scenarios == ()
    assert belief.scenario_capability is CapabilityStatus.LIMITED
    assert parsed.report.validation_status == "DEGRADED"


def test_path_and_distribution_adapters_are_deterministic() -> None:
    path_rows = (
        _path("scenario-a", 1, Decimal("0.01"), Decimal("0.4")),
        _path("scenario-a", 2, Decimal("0.02"), Decimal("0.4")),
        _path("scenario-b", 1, Decimal("0.03"), None),
    )
    indexed = _paths_index((*path_rows, _path("stress", 1, Decimal("0.5"), Decimal("0.6"), "STRESS")))
    assert len(indexed[("AAA", 2)]) == 3
    scenarios = _scenarios_from_paths(path_rows, Decimal("100"))
    assert len(scenarios) == 1
    assert scenarios[0].terminal_underlying_price == Decimal("102")
    assert scenarios[0].probability == Decimal("1")

    empirical = _distribution("EMPIRICAL", {"kind": "EMPIRICAL", "samples": [-0.1, 0, 0.1]})
    generated = _scenarios_from_distribution(empirical, Decimal("100"), 2)
    assert len(generated) == 2
    assert sum((row.probability for row in generated), Decimal("0")) == Decimal("1")
    point = _distribution("POINT", {"kind": "POINT", "value": 0.05})
    assert _distribution_samples(point.distribution) == [Decimal("0.05")]
    assert _stratified_values([Decimal("1"), Decimal("2")], 1) == (Decimal("2"),)
    assert _normalize_scenario_mass(()) == ()


def test_scenario_distribution_and_context_helpers_are_fail_closed() -> None:
    record = _distribution("SCENARIO", {
        "kind": "SCENARIO",
        "scenarios": [
            {"value": 0.1, "probability": 0.75},
            {"value": -2, "probability": 0.25},
            {"value": None, "probability": 0.1},
            "ignored",
        ],
    })
    scenarios = _scenario_distribution(record, Decimal("100"))
    assert len(scenarios) == 1
    assert scenarios[0].probability == Decimal("1")
    assert _distribution_samples({"kind": "UNKNOWN"}) == []

    confidence = P5ForecastConfidenceRecord(
        underlying="AAA",
        target_id="return",
        horizon="1D",
        overall_confidence=Decimal("0.5"),
        confidence_method="method",
        calibration_version="v1",
        calibration_status="PARTIAL",
        abstained=True,
        lineage_id="lineage",
    )
    regime = P5RegimeOODRecord(
        underlying="AAA",
        horizon="1D",
        severity="SEVERE",
        validity_status="VALID",
        regime_probabilities={"HIGH_VOL": Decimal("0.8"), "LOW_VOL": Decimal("0.2")},
        reason_codes=("OOD",),
        lineage_id="lineage",
    )
    assert _confidence_components(None) == {}
    assert _confidence_components(confidence)["calibration"] is None
    assert _regime_context("ORIGINAL", None) == "ORIGINAL"
    assert _regime_context("ORIGINAL", regime) == "HIGH_VOL|OOD_SEVERE|VALID"
    reasons = _capability_reasons(CapabilityStatus.LIMITED, confidence, regime, object(), _belief_stub())
    assert set(reasons) == {"OOD", "P5_ABSTAINED", "P5_SCENARIOS_UNAVAILABLE", "P5_AMBIGUITY_DISTRIBUTIONS_UNRESOLVED"}


def _path(
    scenario_id: str,
    step: int,
    future_return: Decimal,
    probability: Decimal | None,
    scenario_type: str = "NOMINAL",
) -> P5ScenarioPathRecord:
    return P5ScenarioPathRecord(
        underlying="AAA",
        decision_time=DECISION,
        horizon="2D",
        scenario_id=scenario_id,
        scenario_type=scenario_type,
        probability=probability,
        path_step=step,
        path_timestamp=DECISION + timedelta(days=step),
        future_return=future_return,
        jump_state=False,
        seed=1,
        generator_id="test",
        lineage_id="lineage",
    )


def _distribution(family: str, distribution: dict[str, object]) -> P5ReturnDistributionRecord:
    return P5ReturnDistributionRecord(
        underlying="AAA",
        target_id="return",
        horizon="1D",
        decision_time=DECISION,
        distribution=distribution,
        distribution_family=family,
        distribution_version="v1",
        calibration_status="QUALIFIED",
        confidence=Decimal("0.8"),
        lineage_id="lineage",
        units="decimal_return",
    )


class _BeliefStub:
    ambiguity_probabilities: tuple[Decimal, ...] = ()


def _belief_stub() -> _BeliefStub:
    return _BeliefStub()
