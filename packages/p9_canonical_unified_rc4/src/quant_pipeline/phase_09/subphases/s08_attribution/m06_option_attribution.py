"""P9.S8.M06 — option Greek and full-repricing PnL attribution."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field, field_validator, model_validator

from quant_pipeline.phase_09.subphases.s07_prospective_validation.contracts import (
    NonEmptyStr,
    StrictModel,
)

from .canonical import payload_sha256
from .contracts import AttributionQuality


class OptionAttributionInterval(StrictModel):
    position_id: NonEmptyStr
    interval_start: datetime
    interval_end: datetime
    greek_snapshot_time: datetime
    quantity: float
    price_before: float = Field(ge=0.0)
    price_after: float = Field(ge=0.0)
    delta: float
    gamma: float
    vega: float
    theta_per_year: float
    rho: float
    spot_change: float
    volatility_change: float
    year_fraction: float = Field(ge=0.0)
    rate_change: float
    skew_effect: float = 0.0
    term_structure_effect: float = 0.0
    cross_greek_effect: float = 0.0
    lifecycle_pnl: float = 0.0
    surface_available: bool = True

    @field_validator("interval_start", "interval_end", "greek_snapshot_time")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("option attribution clocks must be UTC")
        return value

    @model_validator(mode="after")
    def validate_order(self) -> "OptionAttributionInterval":
        if self.interval_end < self.interval_start:
            raise ValueError("interval_end must be at or after interval_start")
        if self.greek_snapshot_time > self.interval_start:
            raise ValueError("Greek snapshot must not occur after the movement starts")
        return self


class OptionAttributionPolicy(StrictModel):
    residual_tolerance: float = Field(default=1e-4, ge=0.0)
    require_surface: bool = True


class OptionIntervalAttribution(StrictModel):
    position_id: NonEmptyStr
    full_repricing_pnl: float
    delta_pnl: float
    gamma_pnl: float
    vega_pnl: float
    theta_pnl: float
    rho_pnl: float
    skew_pnl: float
    term_structure_pnl: float
    cross_greek_pnl: float
    lifecycle_pnl: float
    explained_pnl: float
    residual_pnl: float
    residual_material: bool
    quality: AttributionQuality
    reason_codes: tuple[NonEmptyStr, ...] = ()


class OptionAttributionResult(StrictModel):
    intervals: tuple[OptionIntervalAttribution, ...]
    full_repricing_pnl: float
    explained_pnl: float
    residual_pnl: float
    quality: AttributionQuality
    reason_codes: tuple[NonEmptyStr, ...]
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def attribute_option_pnl(
    intervals: tuple[OptionAttributionInterval, ...],
    policy: OptionAttributionPolicy,
) -> OptionAttributionResult:
    """Explain option PnL with pre-move Greeks and preserve full-repricing residual."""

    attributed = tuple(_attribute_interval(item, policy) for item in intervals)
    full = sum(item.full_repricing_pnl for item in attributed)
    explained = sum(item.explained_pnl for item in attributed)
    residual = sum(item.residual_pnl for item in attributed)
    reasons = sorted({code for item in attributed for code in item.reason_codes})
    if any(item.quality is AttributionQuality.INVALID for item in attributed):
        quality = AttributionQuality.INVALID
    elif any(item.quality is AttributionQuality.LIMITED for item in attributed):
        quality = AttributionQuality.LIMITED
    elif not attributed:
        quality = AttributionQuality.INSUFFICIENT_EVIDENCE
        reasons.append("P9_ATTRIBUTION_OPTION_SAMPLE_EMPTY")
    else:
        quality = AttributionQuality.QUALIFIED
    payload = {
        "intervals": [item.model_dump(mode="json") for item in attributed],
        "full": full,
        "explained": explained,
        "residual": residual,
        "quality": quality,
        "reason_codes": sorted(set(reasons)),
    }
    return OptionAttributionResult(
        intervals=attributed,
        full_repricing_pnl=full,
        explained_pnl=explained,
        residual_pnl=residual,
        quality=quality,
        reason_codes=tuple(sorted(set(reasons))),
        result_sha256=payload_sha256(payload),
    )


def _attribute_interval(
    item: OptionAttributionInterval,
    policy: OptionAttributionPolicy,
) -> OptionIntervalAttribution:
    multiplier = item.quantity
    delta_pnl = multiplier * item.delta * item.spot_change
    gamma_pnl = multiplier * 0.5 * item.gamma * item.spot_change**2
    vega_pnl = multiplier * item.vega * item.volatility_change
    theta_pnl = multiplier * item.theta_per_year * item.year_fraction
    rho_pnl = multiplier * item.rho * item.rate_change
    skew_pnl = multiplier * item.skew_effect
    term_pnl = multiplier * item.term_structure_effect
    cross_pnl = multiplier * item.cross_greek_effect
    full = multiplier * (item.price_after - item.price_before) + item.lifecycle_pnl
    explained = (
        delta_pnl
        + gamma_pnl
        + vega_pnl
        + theta_pnl
        + rho_pnl
        + skew_pnl
        + term_pnl
        + cross_pnl
        + item.lifecycle_pnl
    )
    residual = full - explained
    reasons: set[str] = set()
    if policy.require_surface and not item.surface_available:
        reasons.add("P9_ATTRIBUTION_VOL_SURFACE_UNAVAILABLE")
    material = abs(residual) > policy.residual_tolerance
    if material:
        reasons.add("P9_ATTRIBUTION_OPTION_RESIDUAL_MATERIAL")
    quality = AttributionQuality.LIMITED if reasons else AttributionQuality.QUALIFIED
    return OptionIntervalAttribution(
        position_id=item.position_id,
        full_repricing_pnl=full,
        delta_pnl=delta_pnl,
        gamma_pnl=gamma_pnl,
        vega_pnl=vega_pnl,
        theta_pnl=theta_pnl,
        rho_pnl=rho_pnl,
        skew_pnl=skew_pnl,
        term_structure_pnl=term_pnl,
        cross_greek_pnl=cross_pnl,
        lifecycle_pnl=item.lifecycle_pnl,
        explained_pnl=explained,
        residual_pnl=residual,
        residual_material=material,
        quality=quality,
        reason_codes=tuple(sorted(reasons)),
    )
