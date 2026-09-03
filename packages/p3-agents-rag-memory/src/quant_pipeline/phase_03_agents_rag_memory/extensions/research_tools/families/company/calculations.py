"""Pure, versioned company calculations."""
from __future__ import annotations

from .request_models import DcfAssumptions, ReverseDcfAssumptions


def scenario_dcf(assumptions: DcfAssumptions) -> dict[str, float]:
    cash_flow = assumptions.base_free_cash_flow
    present_value = 0.0
    for year, growth in enumerate(assumptions.growth_rates, start=1):
        cash_flow *= 1.0 + growth
        present_value += cash_flow / ((1.0 + assumptions.discount_rate) ** year)
    terminal = cash_flow * (1.0 + assumptions.terminal_growth_rate) / (
        assumptions.discount_rate - assumptions.terminal_growth_rate
    )
    terminal_pv = terminal / ((1.0 + assumptions.discount_rate) ** len(assumptions.growth_rates))
    enterprise_value = present_value + terminal_pv
    equity_value = enterprise_value - assumptions.net_debt
    return {
        "enterprise_value": enterprise_value, "equity_value": equity_value,
        "scenario_value_per_share": equity_value / assumptions.shares_outstanding,
        "terminal_value_share": terminal_pv / enterprise_value if enterprise_value else 0.0,
    }


def reverse_dcf(assumptions: ReverseDcfAssumptions) -> dict[str, float | bool]:
    target_equity = assumptions.market_price * assumptions.shares_outstanding
    target_enterprise = target_equity + assumptions.net_debt

    def enterprise_value(growth: float) -> float:
        result = scenario_dcf(DcfAssumptions(
            base_free_cash_flow=assumptions.base_free_cash_flow,
            growth_rates=(growth,) * assumptions.forecast_years,
            discount_rate=assumptions.discount_rate,
            terminal_growth_rate=assumptions.terminal_growth_rate,
            net_debt=assumptions.net_debt,
            shares_outstanding=assumptions.shares_outstanding,
        ))
        return result["enterprise_value"]

    low, high = assumptions.lower_growth, assumptions.upper_growth
    low_value, high_value = enterprise_value(low), enterprise_value(high)
    lower_value, upper_value = sorted((low_value, high_value))
    target_bracketed = lower_value <= target_enterprise <= upper_value
    increasing = high_value >= low_value

    if target_bracketed:
        for _ in range(assumptions.iterations):
            mid = (low + high) / 2.0
            mid_value = enterprise_value(mid)
            if (mid_value < target_enterprise) == increasing:
                low = mid
            else:
                high = mid
        implied = (low + high) / 2.0
    else:
        implied = min(
            (assumptions.lower_growth, assumptions.upper_growth),
            key=lambda growth: abs(enterprise_value(growth) - target_enterprise),
        )

    implied_value = enterprise_value(implied)
    return {
        "implied_annual_growth": implied,
        "market_price": assumptions.market_price,
        "target_enterprise_value": target_enterprise,
        "implied_enterprise_value": implied_value,
        "valuation_residual": implied_value - target_enterprise,
        "target_bracketed": target_bracketed,
    }


def safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0.0):
        return None
    return numerator / denominator
