from datetime import datetime, timezone
from decimal import Decimal

from quant_pipeline.phase_06_strategy_synthesis.domain.enums import (
    CalculationStatus,
    InstrumentType,
    LegRole,
    ObjectiveFamily,
    OriginMode,
    Side,
    TemplateId,
)
from quant_pipeline.phase_06_strategy_synthesis.domain.models import (
    StrategyCandidate,
    StrategyLeg,
    UnderlyingObservation,
)
from quant_pipeline.phase_06_strategy_synthesis.foundation.configuration import (
    Phase6RunConfiguration,
)
from quant_pipeline.phase_06_strategy_synthesis.subphase_07_pricing_scenario_evaluation.services import (
    cost_liquidity,
)

UTC = timezone.utc
NOW = datetime(2026, 1, 2, 20, 0, tzinfo=UTC)


def _candidate() -> StrategyCandidate:
    leg = StrategyLeg(
        leg_id="leg-1",
        instrument_id="XYZ",
        instrument_type=InstrumentType.UNDERLYING,
        side=Side.LONG,
        quantity=Decimal("1"),
        multiplier=Decimal("1"),
        currency="USD",
        exchange="TEST",
        entry_price_reference=Decimal("100"),
        price_selection_method="MIDPOINT",
        leg_role=LegRole.CORE,
    )
    return StrategyCandidate(
        candidate_id="candidate-1",
        candidate_version="1",
        underlying_id="XYZ",
        decision_time=NOW,
        horizon_days=1,
        objective_family=ObjectiveFamily.DIRECTIONAL_UP,
        origin_mode=OriginMode.TEMPLATE,
        origin_template_id=TemplateId.LONG_UNDERLYING,
        legs=(leg,),
        strategy_scale=Decimal("1"),
        generation_run_id="run-1",
        lineage_id="lineage-1",
    )


def _config() -> Phase6RunConfiguration:
    return Phase6RunConfiguration.model_validate({
        "run_id": "run-1",
        "cycle_id": "cycle-1",
        "decision_time": NOW.isoformat(),
        "created_at": NOW.isoformat(),
        "available_at": NOW.isoformat(),
        "seed": 7,
    })


def test_underlying_bid_ask_produces_complete_liquidity_metrics() -> None:
    underlying = UnderlyingObservation(
        underlying_id="XYZ",
        quote_time=NOW,
        available_at=NOW,
        bid=Decimal("99.9"),
        ask=Decimal("100.1"),
        last=Decimal("100"),
        currency="USD",
        exchange="TEST",
        source_artifact_id="underlying-artifact",
        source_record_id="XYZ",
    )
    record = cost_liquidity((_candidate(),), (), (underlying,), _config())[0]
    assert record.status is CalculationStatus.AVAILABLE
    assert record.maximum_relative_spread == Decimal("0.002")
    assert record.weakest_leg_liquidity == Decimal("0.998")
    assert record.slippage_estimate > 0


def test_missing_underlying_two_sided_market_is_explicitly_degraded() -> None:
    underlying = UnderlyingObservation(
        underlying_id="XYZ",
        quote_time=NOW,
        available_at=NOW,
        last=Decimal("100"),
        currency="USD",
        exchange="TEST",
        source_artifact_id="underlying-artifact",
        source_record_id="XYZ",
    )
    record = cost_liquidity((_candidate(),), (), (underlying,), _config())[0]
    assert record.status is CalculationStatus.DEGRADED
    assert record.maximum_relative_spread is None
    assert record.weakest_leg_liquidity is None
