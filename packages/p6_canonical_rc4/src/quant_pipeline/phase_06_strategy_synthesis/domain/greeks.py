"""CPU-first Black-Scholes-Merton Greeks for European option legs."""

from __future__ import annotations

from decimal import Decimal
from math import erf, exp, log, pi, sqrt

from .enums import OptionType, Side
from .models import StrategyLeg


def _norm_cdf(value: float) -> float:
    return 0.5 * (1.0 + erf(value / sqrt(2.0)))


def _norm_pdf(value: float) -> float:
    return exp(-0.5 * value * value) / sqrt(2.0 * pi)


def option_greeks(
    leg: StrategyLeg,
    spot: Decimal,
    volatility: Decimal,
    years: Decimal,
    risk_free_rate: Decimal,
    dividend_yield: Decimal,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    s = float(spot)
    if leg.strike is None:
        raise ValueError("option leg requires strike")
    k = float(leg.strike)
    sigma = float(volatility)
    t = float(years)
    r = float(risk_free_rate)
    q = float(dividend_yield)
    if min(s, k, sigma, t) <= 0:
        raise ValueError("positive spot, strike, volatility, and time are required")
    root_t = sqrt(t)
    d1 = (log(s / k) + (r - q + 0.5 * sigma * sigma) * t) / (sigma * root_t)
    d2 = d1 - sigma * root_t
    discount_q = exp(-q * t)
    discount_r = exp(-r * t)
    if leg.option_type is OptionType.CALL:
        delta = discount_q * _norm_cdf(d1)
        theta = (
            -s * discount_q * _norm_pdf(d1) * sigma / (2 * root_t)
            - r * k * discount_r * _norm_cdf(d2)
            + q * s * discount_q * _norm_cdf(d1)
        ) / 365.0
    else:
        delta = discount_q * (_norm_cdf(d1) - 1)
        theta = (
            -s * discount_q * _norm_pdf(d1) * sigma / (2 * root_t)
            + r * k * discount_r * _norm_cdf(-d2)
            - q * s * discount_q * _norm_cdf(-d1)
        ) / 365.0
    gamma = discount_q * _norm_pdf(d1) / (s * sigma * root_t)
    vega = s * discount_q * _norm_pdf(d1) * root_t / 100.0
    sign = 1.0 if leg.side is Side.LONG else -1.0
    scale = sign * float(leg.quantity * leg.multiplier)
    return tuple(Decimal(str(value * scale)) for value in (delta, gamma, vega, theta))


def option_price(
    leg: StrategyLeg,
    spot: Decimal,
    volatility: Decimal,
    years: Decimal,
    risk_free_rate: Decimal,
    dividend_yield: Decimal,
) -> Decimal:
    """Black-Scholes-Merton mark for one European option leg, including side and scale."""
    s = float(spot)
    if leg.strike is None:
        raise ValueError("option leg requires strike")
    k = float(leg.strike)
    sigma = float(volatility)
    t = float(years)
    r = float(risk_free_rate)
    q = float(dividend_yield)
    if min(s, k) <= 0:
        raise ValueError("positive spot and strike are required")
    if t <= 0 or sigma <= 0:
        intrinsic = max(s - k, 0.0) if leg.option_type is OptionType.CALL else max(k - s, 0.0)
        value = intrinsic
    else:
        root_t = sqrt(t)
        d1 = (log(s / k) + (r - q + 0.5 * sigma * sigma) * t) / (sigma * root_t)
        d2 = d1 - sigma * root_t
        discount_q = exp(-q * t)
        discount_r = exp(-r * t)
        if leg.option_type is OptionType.CALL:
            value = s * discount_q * _norm_cdf(d1) - k * discount_r * _norm_cdf(d2)
        else:
            value = k * discount_r * _norm_cdf(-d2) - s * discount_q * _norm_cdf(-d1)
    sign = 1.0 if leg.side is Side.LONG else -1.0
    scale = sign * float(leg.quantity * leg.multiplier)
    return Decimal(str(value * scale))
