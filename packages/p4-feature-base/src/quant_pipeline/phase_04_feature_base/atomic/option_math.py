from __future__ import annotations

import math

from scipy.optimize import brentq
from scipy.stats import norm

from ..economic_errors import NumericDomainError


def black_scholes_price(
    *, spot: float, strike: float, time_to_expiry: float, rate: float, dividend_yield: float,
    volatility: float, option_type: str,
) -> float:
    if min(spot, strike, time_to_expiry, volatility) <= 0:
        raise NumericDomainError("P4_S4_OPTION_DOMAIN", "spot, strike, time and volatility must be positive")
    sigma_sqrt_t = volatility * math.sqrt(time_to_expiry)
    d1 = (math.log(spot / strike) + (rate - dividend_yield + 0.5 * volatility**2) * time_to_expiry) / sigma_sqrt_t
    d2 = d1 - sigma_sqrt_t
    discount_q = math.exp(-dividend_yield * time_to_expiry)
    discount_r = math.exp(-rate * time_to_expiry)
    if option_type.upper() == "C":
        return spot * discount_q * norm.cdf(d1) - strike * discount_r * norm.cdf(d2)
    if option_type.upper() == "P":
        return strike * discount_r * norm.cdf(-d2) - spot * discount_q * norm.cdf(-d1)
    raise NumericDomainError("P4_S4_OPTION_TYPE", f"unsupported option type: {option_type}")


def implied_volatility(
    *, price: float, spot: float, strike: float, time_to_expiry: float, rate: float,
    dividend_yield: float, option_type: str, maximum_volatility: float = 5.0,
) -> float | None:
    if min(price, spot, strike, time_to_expiry) <= 0:
        return None
    lower_price = black_scholes_price(
        spot=spot, strike=strike, time_to_expiry=time_to_expiry, rate=rate,
        dividend_yield=dividend_yield, volatility=1e-6, option_type=option_type,
    )
    upper_price = black_scholes_price(
        spot=spot, strike=strike, time_to_expiry=time_to_expiry, rate=rate,
        dividend_yield=dividend_yield, volatility=maximum_volatility, option_type=option_type,
    )
    if price < lower_price - 1e-10 or price > upper_price + 1e-10:
        return None
    try:
        return float(brentq(
            lambda sigma: black_scholes_price(
                spot=spot, strike=strike, time_to_expiry=time_to_expiry, rate=rate,
                dividend_yield=dividend_yield, volatility=sigma, option_type=option_type,
            ) - price,
            1e-6,
            maximum_volatility,
            xtol=1e-10,
            rtol=1e-10,
            maxiter=100,
        ))
    except ValueError:
        return None
