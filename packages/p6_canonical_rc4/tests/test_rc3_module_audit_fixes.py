from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_06_strategy_synthesis.boundaries.p5_manifest import _artifact_sources
from quant_pipeline.phase_06_strategy_synthesis.boundaries.p5_scenarios import _scenarios_from_distribution
from quant_pipeline.phase_06_strategy_synthesis.domain.market_models import UnderlyingObservation
from quant_pipeline.phase_06_strategy_synthesis.domain.market_price import reference_spot
from quant_pipeline.phase_06_strategy_synthesis.foundation.configuration import P5CompatibilityPolicy
from quant_pipeline.phase_06_strategy_synthesis.foundation.errors import Phase6ContractError


def _observation(*, bid=None, ask=None, last=None):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return UnderlyingObservation(
        underlying_id="ABC", quote_time=now, available_at=now,
        bid=bid, ask=ask, last=last, currency="USD", exchange="X",
        source_artifact_id="a", source_record_id="r",
    )


def test_reference_spot_is_canonical_midpoint_then_fallback() -> None:
    assert reference_spot(_observation(bid=Decimal("99"), ask=Decimal("101"), last=Decimal("98"))) == Decimal("100")
    assert reference_spot(_observation(last=Decimal("98"))) == Decimal("98")


def test_conflicting_embedded_and_direct_p5_artifacts_fail_closed() -> None:
    inputs = {
        "phase5_output_handoff_manifest": {"embedded_v2_artifacts": {"market_belief_state": {"x": 1}}},
        "market_belief_state": {"x": 2},
    }
    with pytest.raises(Phase6ContractError) as exc:
        _artifact_sources(inputs, "P6.S1.M01")
    assert exc.value.reason_code == "P6_P5_ARTIFACT_SOURCE_CONFLICT"


def test_identical_embedded_and_direct_p5_artifacts_are_accepted() -> None:
    artifact = {"x": 1, "records": []}
    inputs = {
        "phase5_output_handoff_manifest": {"embedded_v2_artifacts": {"market_belief_state": artifact}},
        "market_belief_state": dict(artifact),
    }
    assert _artifact_sources(inputs, "P6.S1.M01")["market_belief_state"] == artifact


def test_parametric_distribution_uses_published_quantiles_and_audits_mass() -> None:
    record = SimpleNamespace(
        distribution={"kind": "PARAMETRIC", "family": "NORMAL", "location": 0.0, "scale": 0.1},
        quantiles=(
            {"level": 0.01, "value": -0.25},
            {"level": 0.05, "value": -0.15},
            {"level": 0.50, "value": 0.0},
            {"level": 0.95, "value": 0.15},
            {"level": 0.99, "value": 0.25},
        ),
        lineage_id="lin",
    )
    scenarios, audit, source = _scenarios_from_distribution(record, Decimal("100"), 101, include_audit=True)
    assert source == "P5_RETURN_DISTRIBUTION_QUANTILE_APPROXIMATION"
    assert len(scenarios) == 5
    assert sum(row.probability for row in scenarios) == Decimal("1")
    assert audit["original_probability_mass"] == Decimal("1")
    assert audit["rejected_probability_mass"] == Decimal("0")


def test_negative_terminal_mass_is_explicitly_recorded() -> None:
    record = SimpleNamespace(
        distribution={
            "kind": "SCENARIOS",
            "scenarios": [
                {"value": -2.0, "probability": 0.2},
                {"value": 0.1, "probability": 0.8},
            ],
        },
        quantiles=(), lineage_id="lin",
    )
    scenarios, audit, _ = _scenarios_from_distribution(record, Decimal("100"), 101, include_audit=True)
    assert len(scenarios) == 1
    assert scenarios[0].probability == Decimal("1")
    assert audit["rejected_probability_mass"] == Decimal("0.2")
    assert audit["normalization_factor"] == Decimal("1.25")
    assert audit["renormalized"] is True


def test_horizon_time_basis_is_explicit_and_closed() -> None:
    assert P5CompatibilityPolicy().horizon_time_basis == "CALENDAR_DAYS"
    with pytest.raises(ValidationError):
        P5CompatibilityPolicy(horizon_time_basis="TRADING_SESSIONS")
