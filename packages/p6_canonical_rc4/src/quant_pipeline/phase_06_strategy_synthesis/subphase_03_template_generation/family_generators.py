"""Wave 1 template-family generators with explicit defined-risk structures."""

from __future__ import annotations

from ..domain.enums import LegRole, ObjectiveFamily, OptionType, Side, TemplateId
from ..domain.models import ExecutableQuote, OptionContractReference
from ..foundation.configuration import Phase6RunConfiguration
from .builders import CandidateAppender, option_leg, underlying_leg
from .planning import TemplatePlan


def generate_single(
    plan: TemplatePlan,
    underlying_id: str,
    calls: tuple[OptionContractReference, ...],
    puts: tuple[OptionContractReference, ...],
    configuration: Phase6RunConfiguration,
    add: CandidateAppender,
) -> None:
    """Generate atomic underlying and long-option candidates."""
    quotes = plan.quote_by_id
    if configuration.strategy.allow_long_underlying:
        add(
            TemplateId.LONG_UNDERLYING,
            ObjectiveFamily.DIRECTIONAL_UP,
            [underlying_leg(plan, underlying_id, Side.LONG, LegRole.CORE)],
        )
    if configuration.strategy.allow_short_underlying:
        add(
            TemplateId.SHORT_UNDERLYING,
            ObjectiveFamily.DIRECTIONAL_DOWN,
            [underlying_leg(plan, underlying_id, Side.SHORT, LegRole.CORE)],
        )
    spot = plan.spot(underlying_id)
    if calls:
        contract = min(calls, key=lambda item: abs(item.strike - spot))
        add(
            TemplateId.LONG_CALL,
            ObjectiveFamily.DIRECTIONAL_UP,
            [option_leg(contract, quotes[contract.contract_id], Side.LONG, 1, LegRole.CORE)],
        )
    if puts:
        contract = min(puts, key=lambda item: abs(item.strike - spot))
        add(
            TemplateId.LONG_PUT,
            ObjectiveFamily.DIRECTIONAL_DOWN,
            [option_leg(contract, quotes[contract.contract_id], Side.LONG, 1, LegRole.CORE)],
        )


def generate_verticals(
    plan: TemplatePlan,
    underlying_id: str,
    calls: tuple[OptionContractReference, ...],
    puts: tuple[OptionContractReference, ...],
    configuration: Phase6RunConfiguration,
    add: CandidateAppender,
) -> None:
    """Generate debit and defined-risk credit verticals."""
    del underlying_id, configuration
    quotes = plan.quote_by_id
    if len(calls) >= 2:
        low, high = calls[0], calls[-1]
        add(
            TemplateId.BULL_CALL_DEBIT,
            ObjectiveFamily.DIRECTIONAL_UP,
            [
                option_leg(low, quotes[low.contract_id], Side.LONG, 1, LegRole.CORE),
                option_leg(high, quotes[high.contract_id], Side.SHORT, 1, LegRole.FINANCING),
            ],
        )
        add(
            TemplateId.BEAR_CALL_CREDIT,
            ObjectiveFamily.INCOME_DEFINED_RISK,
            [
                option_leg(low, quotes[low.contract_id], Side.SHORT, 1, LegRole.FINANCING),
                option_leg(high, quotes[high.contract_id], Side.LONG, 1, LegRole.PROTECTION),
            ],
        )
    if len(puts) >= 2:
        low, high = puts[0], puts[-1]
        add(
            TemplateId.BEAR_PUT_DEBIT,
            ObjectiveFamily.DIRECTIONAL_DOWN,
            [
                option_leg(high, quotes[high.contract_id], Side.LONG, 1, LegRole.CORE),
                option_leg(low, quotes[low.contract_id], Side.SHORT, 1, LegRole.FINANCING),
            ],
        )
        add(
            TemplateId.BULL_PUT_CREDIT,
            ObjectiveFamily.INCOME_DEFINED_RISK,
            [
                option_leg(high, quotes[high.contract_id], Side.SHORT, 1, LegRole.FINANCING),
                option_leg(low, quotes[low.contract_id], Side.LONG, 1, LegRole.PROTECTION),
            ],
        )


def generate_volatility(
    plan: TemplatePlan,
    underlying_id: str,
    calls: tuple[OptionContractReference, ...],
    puts: tuple[OptionContractReference, ...],
    configuration: Phase6RunConfiguration,
    add: CandidateAppender,
) -> None:
    """Generate long-volatility and defined-risk range structures."""
    del configuration
    if not calls or not puts:
        raise ValueError("call and put contracts are required")
    quotes = plan.quote_by_id
    spot = plan.spot(underlying_id)
    call = min(calls, key=lambda item: abs(item.strike - spot))
    put = min(puts, key=lambda item: abs(item.strike - spot))
    if call.strike == put.strike:
        add(
            TemplateId.LONG_STRADDLE,
            ObjectiveFamily.LONG_VOLATILITY,
            [
                option_leg(call, quotes[call.contract_id], Side.LONG, 1, LegRole.CORE),
                option_leg(put, quotes[put.contract_id], Side.LONG, 1, LegRole.CORE),
            ],
        )
    low_put = max(
        (item for item in puts if item.strike < spot),
        key=lambda item: item.strike,
    )
    high_call = min(
        (item for item in calls if item.strike > spot),
        key=lambda item: item.strike,
    )
    add(
        TemplateId.LONG_STRANGLE,
        ObjectiveFamily.LONG_VOLATILITY,
        [
            option_leg(low_put, quotes[low_put.contract_id], Side.LONG, 1, LegRole.CORE),
            option_leg(high_call, quotes[high_call.contract_id], Side.LONG, 1, LegRole.CORE),
        ],
    )
    _add_call_butterfly(calls, quotes, add)
    _add_call_condor(calls, quotes, add)
    _add_iron_structures(calls, puts, quotes, add)


def _add_call_butterfly(
    calls: tuple[OptionContractReference, ...],
    quotes: dict[str, ExecutableQuote],
    add: CandidateAppender,
) -> None:
    if len(calls) < 3:
        return
    low, middle, high = calls[0], calls[len(calls) // 2], calls[-1]
    add(
        TemplateId.LONG_CALL_BUTTERFLY,
        ObjectiveFamily.POSITIVE_CONVEXITY,
        [
            option_leg(low, quotes[low.contract_id], Side.LONG, 1, LegRole.CORE),
            option_leg(middle, quotes[middle.contract_id], Side.SHORT, 2, LegRole.FINANCING),
            option_leg(high, quotes[high.contract_id], Side.LONG, 1, LegRole.PROTECTION),
        ],
    )


def _add_call_condor(
    calls: tuple[OptionContractReference, ...],
    quotes: dict[str, ExecutableQuote],
    add: CandidateAppender,
) -> None:
    if len(calls) < 4:
        return
    low, lower_middle, upper_middle, high = calls[0], calls[1], calls[-2], calls[-1]
    add(
        TemplateId.LONG_CALL_CONDOR,
        ObjectiveFamily.RANGE,
        [
            option_leg(low, quotes[low.contract_id], Side.LONG, 1, LegRole.CORE),
            option_leg(
                lower_middle,
                quotes[lower_middle.contract_id],
                Side.SHORT,
                1,
                LegRole.FINANCING,
            ),
            option_leg(
                upper_middle,
                quotes[upper_middle.contract_id],
                Side.SHORT,
                1,
                LegRole.FINANCING,
            ),
            option_leg(high, quotes[high.contract_id], Side.LONG, 1, LegRole.PROTECTION),
        ],
    )


def _add_iron_structures(
    calls: tuple[OptionContractReference, ...],
    puts: tuple[OptionContractReference, ...],
    quotes: dict[str, ExecutableQuote],
    add: CandidateAppender,
) -> None:
    if len(calls) < 2 or len(puts) < 2:
        return
    long_put, short_put = puts[0], puts[-1]
    short_call, long_call = calls[0], calls[-1]
    add(
        TemplateId.IRON_BUTTERFLY,
        ObjectiveFamily.SHORT_VOLATILITY_DEFINED_RISK,
        [
            option_leg(long_put, quotes[long_put.contract_id], Side.LONG, 1, LegRole.PROTECTION),
            option_leg(short_put, quotes[short_put.contract_id], Side.SHORT, 1, LegRole.FINANCING),
            option_leg(short_call, quotes[short_call.contract_id], Side.SHORT, 1, LegRole.FINANCING),
            option_leg(long_call, quotes[long_call.contract_id], Side.LONG, 1, LegRole.PROTECTION),
        ],
    )
    add(
        TemplateId.IRON_CONDOR,
        ObjectiveFamily.SHORT_VOLATILITY_DEFINED_RISK,
        [
            option_leg(long_put, quotes[long_put.contract_id], Side.LONG, 1, LegRole.PROTECTION),
            option_leg(puts[-2], quotes[puts[-2].contract_id], Side.SHORT, 1, LegRole.FINANCING),
            option_leg(calls[1], quotes[calls[1].contract_id], Side.SHORT, 1, LegRole.FINANCING),
            option_leg(long_call, quotes[long_call.contract_id], Side.LONG, 1, LegRole.PROTECTION),
        ],
    )


def generate_skew(
    plan: TemplatePlan,
    underlying_id: str,
    calls: tuple[OptionContractReference, ...],
    puts: tuple[OptionContractReference, ...],
    configuration: Phase6RunConfiguration,
    add: CandidateAppender,
) -> None:
    """Generate collars and protected skew-expression structures."""
    if not calls or not puts:
        raise ValueError("call and put contracts are required")
    quotes = plan.quote_by_id
    spot = plan.spot(underlying_id)
    put = max(
        (item for item in puts if item.strike < spot),
        key=lambda item: item.strike,
    )
    call = min(
        (item for item in calls if item.strike > spot),
        key=lambda item: item.strike,
    )
    add(
        TemplateId.COLLAR,
        ObjectiveFamily.PORTFOLIO_HEDGE,
        [
            underlying_leg(plan, underlying_id, Side.LONG, LegRole.CORE),
            option_leg(put, quotes[put.contract_id], Side.LONG, 1, LegRole.PROTECTION),
            option_leg(call, quotes[call.contract_id], Side.SHORT, 1, LegRole.FINANCING),
        ],
    )
    if configuration.strategy.allow_cash_secured_short_put:
        add(
            TemplateId.RISK_REVERSAL_DEFINED_RISK,
            ObjectiveFamily.SKEW_RELATIVE_VALUE,
            [
                option_leg(put, quotes[put.contract_id], Side.SHORT, 1, LegRole.FINANCING),
                option_leg(call, quotes[call.contract_id], Side.LONG, 1, LegRole.CORE),
            ],
        )
    _add_protected_ratio(calls, quotes, add)


def _add_protected_ratio(
    calls: tuple[OptionContractReference, ...],
    quotes: dict[str, ExecutableQuote],
    add: CandidateAppender,
) -> None:
    if len(calls) < 3:
        return
    low, middle, high = calls[0], calls[len(calls) // 2], calls[-1]
    add(
        TemplateId.PROTECTED_RATIO_CALL,
        ObjectiveFamily.HYBRID,
        [
            option_leg(low, quotes[low.contract_id], Side.LONG, 1, LegRole.CORE),
            option_leg(middle, quotes[middle.contract_id], Side.SHORT, 2, LegRole.FINANCING),
            option_leg(high, quotes[high.contract_id], Side.LONG, 1, LegRole.PROTECTION),
        ],
    )


def generate_reserved(
    plan: TemplatePlan,
    underlying_id: str,
    calls: tuple[OptionContractReference, ...],
    puts: tuple[OptionContractReference, ...],
    configuration: Phase6RunConfiguration,
    add: CandidateAppender,
) -> None:
    """Reserve term-structure and overlay families for Wave 2."""
    del plan, underlying_id, calls, puts, configuration, add
