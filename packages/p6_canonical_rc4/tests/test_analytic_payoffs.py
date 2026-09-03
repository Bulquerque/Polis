"""Analytic payoff reconciliation for known Wave 1 strategy structures."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from conftest import DECISION_TIME
from quant_pipeline.phase_06_strategy_synthesis.domain.enums import (
    ExerciseStyle,
    InstrumentType,
    LegRole,
    OptionType,
    SettlementType,
    Side,
)
from quant_pipeline.phase_06_strategy_synthesis.domain.models import StrategyLeg
from quant_pipeline.phase_06_strategy_synthesis.domain.payoff import strategy_terminal_pnl

D = Decimal
EXPIRATION = DECISION_TIME + timedelta(days=30)


def option_leg(
    identifier: str,
    option_type: OptionType,
    strike: str,
    side: Side,
    premium: str,
    quantity: str = "1",
) -> StrategyLeg:
    return StrategyLeg(
        leg_id=identifier,
        instrument_id=identifier,
        instrument_type=InstrumentType.OPTION,
        side=side,
        quantity=D(quantity),
        option_type=option_type,
        strike=D(strike),
        expiration=EXPIRATION,
        exercise_style=ExerciseStyle.EUROPEAN,
        settlement_type=SettlementType.CASH,
        multiplier=D("1"),
        currency="USD",
        exchange="TEST",
        entry_price_reference=D(premium),
        price_selection_method="TEST",
        leg_role=LegRole.CORE,
    )


def underlying_leg(side: Side, price: str = "100") -> StrategyLeg:
    return StrategyLeg(
        leg_id=f"underlying-{side.value}",
        instrument_id="UNDERLYING",
        instrument_type=InstrumentType.UNDERLYING,
        side=side,
        quantity=D("1"),
        multiplier=D("1"),
        currency="USD",
        exchange="TEST",
        entry_price_reference=D(price),
        price_selection_method="TEST",
        leg_role=LegRole.CORE,
    )


CASES = (
    (
        "long_call",
        (option_leg("c100", OptionType.CALL, "100", Side.LONG, "5"),),
        D("120"),
        D("15"),
    ),
    (
        "long_put",
        (option_leg("p100", OptionType.PUT, "100", Side.LONG, "4"),),
        D("80"),
        D("16"),
    ),
    (
        "bull_call_vertical",
        (
            option_leg("c90", OptionType.CALL, "90", Side.LONG, "12"),
            option_leg("c110", OptionType.CALL, "110", Side.SHORT, "4"),
        ),
        D("120"),
        D("12"),
    ),
    (
        "long_straddle",
        (
            option_leg("c100", OptionType.CALL, "100", Side.LONG, "5"),
            option_leg("p100", OptionType.PUT, "100", Side.LONG, "4"),
        ),
        D("120"),
        D("11"),
    ),
    (
        "long_strangle",
        (
            option_leg("p90", OptionType.PUT, "90", Side.LONG, "2"),
            option_leg("c110", OptionType.CALL, "110", Side.LONG, "3"),
        ),
        D("130"),
        D("15"),
    ),
    (
        "call_butterfly",
        (
            option_leg("c90", OptionType.CALL, "90", Side.LONG, "12"),
            option_leg("c100", OptionType.CALL, "100", Side.SHORT, "7", "2"),
            option_leg("c110", OptionType.CALL, "110", Side.LONG, "4"),
        ),
        D("100"),
        D("8"),
    ),
    (
        "iron_condor",
        (
            option_leg("p80", OptionType.PUT, "80", Side.LONG, "1"),
            option_leg("p90", OptionType.PUT, "90", Side.SHORT, "3"),
            option_leg("c110", OptionType.CALL, "110", Side.SHORT, "3"),
            option_leg("c120", OptionType.CALL, "120", Side.LONG, "1"),
        ),
        D("100"),
        D("4"),
    ),
    (
        "collar",
        (
            underlying_leg(Side.LONG),
            option_leg("p90", OptionType.PUT, "90", Side.LONG, "2"),
            option_leg("c110", OptionType.CALL, "110", Side.SHORT, "3"),
        ),
        D("120"),
        D("11"),
    ),
    (
        "protected_ratio",
        (
            option_leg("c90", OptionType.CALL, "90", Side.LONG, "12"),
            option_leg("c100", OptionType.CALL, "100", Side.SHORT, "6", "2"),
            option_leg("c120", OptionType.CALL, "120", Side.LONG, "1"),
        ),
        D("150"),
        D("-11"),
    ),
)


@pytest.mark.parametrize(("name", "legs", "spot", "expected"), CASES)
def test_known_strategy_payoffs(
    name: str,
    legs: tuple[StrategyLeg, ...],
    spot: Decimal,
    expected: Decimal,
) -> None:
    del name
    assert strategy_terminal_pnl(legs, spot) == expected
