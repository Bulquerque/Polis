from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from statistics import median

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.market.normalization import (
    optional_float,
    parse_date,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.market.result_contracts import (
    SurfaceDiagnosticSummary,
    SurfaceSliceDiagnostic,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.market.types import (
    OptionType,
    SurfaceDiagnosticStatus,
)


def build_surface_summary(
    *,
    underlying: str,
    decision_time: datetime,
    quote_rows: Sequence[Mapping[str, object]],
    spot: float | None,
    minimum_strikes_per_expiry: int,
) -> SurfaceDiagnosticSummary:
    grouped: dict[tuple[date, OptionType], list[Mapping[str, object]]] = defaultdict(list)
    for row in quote_rows:
        expiration = parse_date(row.get("expiration_date"), field="expiration_date")
        option_type = _option_type(row.get("option_type"))
        grouped[(expiration, option_type)].append(row)

    slices = tuple(
        _slice(
            expiration=expiration,
            option_type=option_type,
            rows=tuple(rows),
            spot=spot,
            minimum_strikes=minimum_strikes_per_expiry,
        )
        for (expiration, option_type), rows in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1].value))
    )
    calendar_violations = _calendar_variance_violations(slices, decision_time)
    warnings: list[str] = []
    if spot is None:
        warnings.append("UNDERLYING_SPOT_UNAVAILABLE")
    if any(item.diagnostic_status is not SurfaceDiagnosticStatus.OBSERVED_IV for item in slices):
        warnings.append("PARTIAL_IV_COVERAGE")
    return SurfaceDiagnosticSummary(
        underlying=underlying,
        decision_time=decision_time,
        underlying_spot=spot,
        slices=slices,
        calendar_variance_violations=calendar_violations,
        warnings=tuple(sorted(set(warnings))),
    )


def _slice(
    *,
    expiration: date,
    option_type: OptionType,
    rows: tuple[Mapping[str, object], ...],
    spot: float | None,
    minimum_strikes: int,
) -> SurfaceSliceDiagnostic:
    ordered = tuple(sorted(rows, key=lambda row: float(row.get("strike") or 0.0)))
    strikes = [optional_float(row.get("strike"), field="strike", positive=True) for row in ordered]
    valid_strikes = [value for value in strikes if value is not None]
    ivs = [
        optional_float(
            row.get("iv") if row.get("iv") not in (None, "") else row.get("implied_volatility"),
            field="implied_volatility",
            nonnegative=True,
        )
        for row in ordered
    ]
    observed_pairs = _aggregate_by_strike(
        (strike, iv)
        for strike, iv in zip(strikes, ivs, strict=True)
        if strike is not None and iv is not None
    )
    mids = [_mid(row) for row in ordered]
    executable = [str(row.get("execution_status") or "").upper() == "EXECUTABLE" for row in ordered]
    two_sided = [row.get("bid") is not None and row.get("ask") is not None for row in ordered]
    status = _status(len(set(valid_strikes)), len(observed_pairs), minimum_strikes)
    warnings: list[str] = []
    if len(set(valid_strikes)) < minimum_strikes:
        warnings.append("INSUFFICIENT_STRIKE_COVERAGE")
    if not observed_pairs:
        warnings.append("OBSERVED_IV_UNAVAILABLE")
    atm_iv = _atm_iv(observed_pairs, spot)
    skew = _skew_slope(observed_pairs, spot)
    monotonicity, convexity = _static_price_diagnostics(strikes, mids, option_type)
    if monotonicity:
        warnings.append("PRICE_MONOTONICITY_VIOLATION")
    if convexity:
        warnings.append("PRICE_CONVEXITY_VIOLATION")
    return SurfaceSliceDiagnostic(
        expiration_date=expiration,
        option_type=option_type,
        quote_count=len(ordered),
        strike_count=len(set(valid_strikes)),
        executable_quote_fraction=sum(executable) / len(ordered) if ordered else 0.0,
        two_sided_quote_fraction=sum(two_sided) / len(ordered) if ordered else 0.0,
        observed_iv_fraction=len(observed_pairs) / len(ordered) if ordered else 0.0,
        minimum_strike=min(valid_strikes) if valid_strikes else None,
        maximum_strike=max(valid_strikes) if valid_strikes else None,
        median_iv=median(iv for _, iv in observed_pairs) if observed_pairs else None,
        atm_iv=atm_iv,
        skew_slope=skew,
        price_monotonicity_violations=monotonicity,
        convexity_violations=convexity,
        diagnostic_status=status,
        warnings=tuple(sorted(set(warnings))),
    )


def _status(strikes: int, observed_ivs: int, minimum: int) -> SurfaceDiagnosticStatus:
    if strikes < minimum:
        return SurfaceDiagnosticStatus.INSUFFICIENT_COVERAGE
    if observed_ivs >= minimum:
        return SurfaceDiagnosticStatus.OBSERVED_IV
    return SurfaceDiagnosticStatus.QUOTE_ONLY


def _mid(row: Mapping[str, object]) -> float | None:
    bid = optional_float(row.get("bid"), field="bid", nonnegative=True)
    ask = optional_float(row.get("ask"), field="ask", nonnegative=True)
    if bid is not None and ask is not None and ask >= bid:
        return (bid + ask) / 2.0
    return optional_float(row.get("last_price"), field="last_price", nonnegative=True)


def _atm_iv(pairs: Sequence[tuple[float, float]], spot: float | None) -> float | None:
    if spot is None or spot <= 0 or not pairs:
        return None
    return min(pairs, key=lambda item: abs(math.log(item[0] / spot)))[1]


def _skew_slope(pairs: Sequence[tuple[float, float]], spot: float | None) -> float | None:
    if spot is None or spot <= 0 or len(pairs) < 2:
        return None
    points = [(math.log(strike / spot), iv) for strike, iv in pairs if strike > 0]
    if len(points) < 2:
        return None
    mean_x = sum(x for x, _ in points) / len(points)
    mean_y = sum(y for _, y in points) / len(points)
    denominator = sum((x - mean_x) ** 2 for x, _ in points)
    if math.isclose(denominator, 0.0):
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in points) / denominator


def _aggregate_by_strike(pairs) -> list[tuple[float, float]]:
    grouped: dict[float, list[float]] = defaultdict(list)
    for strike, value in pairs:
        grouped[float(strike)].append(float(value))
    return [(strike, median(values)) for strike, values in sorted(grouped.items())]


def _static_price_diagnostics(
    strikes: Sequence[float | None],
    prices: Sequence[float | None],
    option_type: OptionType,
) -> tuple[int, int]:
    points = _aggregate_by_strike(
        (strike, price)
        for strike, price in zip(strikes, prices, strict=True)
        if strike is not None and price is not None
    )
    if len(points) < 2:
        return 0, 0
    monotonicity = 0
    for (_, left), (_, right) in zip(points, points[1:], strict=False):
        if option_type is OptionType.CALL and right > left + 1e-12:
            monotonicity += 1
        if option_type is OptionType.PUT and right + 1e-12 < left:
            monotonicity += 1
    slopes = [
        (right_price - left_price) / (right_strike - left_strike)
        for (left_strike, left_price), (right_strike, right_price) in zip(points, points[1:], strict=False)
        if right_strike > left_strike
    ]
    convexity = sum(next_slope + 1e-12 < slope for slope, next_slope in zip(slopes, slopes[1:], strict=False))
    return monotonicity, convexity


def _calendar_variance_violations(
    slices: Sequence[SurfaceSliceDiagnostic],
    decision_time: datetime,
) -> int:
    by_type: dict[OptionType | None, list[tuple[float, float]]] = defaultdict(list)
    for item in slices:
        if item.atm_iv is None:
            continue
        days = (item.expiration_date - decision_time.date()).days
        if days <= 0:
            continue
        total_variance = item.atm_iv**2 * (days / 365.0)
        by_type[item.option_type].append((days, total_variance))
    violations = 0
    for values in by_type.values():
        ordered = sorted(values)
        violations += sum(right + 1e-12 < left for (_, left), (_, right) in zip(ordered, ordered[1:], strict=False))
    return violations


def _option_type(value: object) -> OptionType:
    token = str(value or "UNKNOWN").upper()
    if token in {"CALL", "C"}:
        return OptionType.CALL
    if token in {"PUT", "P"}:
        return OptionType.PUT
    return OptionType.UNKNOWN
