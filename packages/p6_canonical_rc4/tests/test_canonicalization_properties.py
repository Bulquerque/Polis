from decimal import Decimal

from conftest import DECISION_TIME
from quant_pipeline.phase_06_strategy_synthesis.domain.enums import (
    InstrumentType,
    LegRole,
    ObjectiveFamily,
    OriginMode,
    Side,
    TemplateId,
)
from quant_pipeline.phase_06_strategy_synthesis.domain.identity import candidate_id, shape_fingerprint
from quant_pipeline.phase_06_strategy_synthesis.domain.models import StrategyCandidate, StrategyLeg


def make_leg(instrument: str, side: Side, quantity: int) -> StrategyLeg:
    return StrategyLeg(
        leg_id=f"{instrument}-{side}-{quantity}",
        instrument_id=instrument,
        instrument_type=InstrumentType.UNDERLYING,
        side=side,
        quantity=Decimal(quantity),
        multiplier=Decimal("1"),
        currency="USD",
        exchange="TEST",
        entry_price_reference=Decimal("100"),
        price_selection_method="TEST",
        leg_role=LegRole.CORE,
    )


def test_candidate_identity_is_order_invariant_exhaustive():
    for left in range(1, 6):
        for right in range(1, 6):
            legs = (make_leg("A", Side.LONG, left), make_leg("B", Side.SHORT, right))
            first = candidate_id(
                underlying_id="X",
                decision_time=DECISION_TIME.isoformat(),
                legs=legs,
                objective_family="HYBRID",
                policy_version="v1",
                horizon_days=1,
            )
            second = candidate_id(
                underlying_id="X",
                decision_time=DECISION_TIME.isoformat(),
                legs=tuple(reversed(legs)),
                objective_family="HYBRID",
                policy_version="v1",
                horizon_days=1,
            )
            assert first == second


def test_equivalent_scale_has_same_shape_fingerprint_exhaustive():
    base = StrategyCandidate(
        candidate_id="a",
        candidate_version="1",
        underlying_id="X",
        decision_time=DECISION_TIME,
        horizon_days=1,
        objective_family=ObjectiveFamily.HYBRID,
        origin_mode=OriginMode.TEMPLATE,
        origin_template_id=TemplateId.LONG_UNDERLYING,
        legs=(make_leg("A", Side.LONG, 1), make_leg("B", Side.SHORT, 1)),
        strategy_scale=Decimal("1"),
        generation_run_id="r",
        lineage_id="l",
    )
    for scale in range(1, 6):
        scaled = base.model_copy(
            update={
                "candidate_id": f"b-{scale}",
                "legs": tuple(
                    leg.model_copy(update={"quantity": leg.quantity * scale})
                    for leg in base.legs
                ),
            }
        )
        assert shape_fingerprint(base)[0] == shape_fingerprint(scaled)[0]
        assert shape_fingerprint(scaled)[1] == Decimal(scale)
