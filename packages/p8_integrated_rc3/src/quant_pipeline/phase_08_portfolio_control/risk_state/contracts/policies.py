"""Version-ready immutable policy surfaces for S4 calculations."""
from pydantic import Field

from .base import StrictModel


class PnLPolicy(StrictModel):
    use_reduced_scenarios: bool = True
    option_volatility_floor: float = Field(default=1e-4, gt=0.0)
    option_spot_floor: float = Field(default=1e-8, gt=0.0)


class DependencePolicy(StrictModel):
    shrinkage_alpha: float | None = Field(default=None, ge=0.0, le=1.0)
    tail_probability: float = Field(default=0.10, gt=0.0, lt=0.5)
    psd_floor: float = Field(default=1e-10, ge=0.0)
    max_psd_repair_relative: float = Field(default=0.25, ge=0.0)
    minimum_effective_samples: float = Field(default=20.0, ge=2.0)


class GreekPolicy(StrictModel):
    reconciliation_tolerance: float = Field(default=1e-8, ge=0.0)
    approximation_error_max: float = Field(default=0.25, ge=0.0)


class LiquidityPolicy(StrictModel):
    max_quote_age_seconds: float = Field(default=300.0, gt=0.0)
    depth_multiplier: float = Field(default=1.0, gt=0.0)
    volume_participation: float = Field(default=0.05, gt=0.0, le=1.0)
    open_interest_participation: float = Field(default=0.02, gt=0.0, le=1.0)
    max_spread_bps: float = Field(default=500.0, gt=0.0)
    min_fill_probability: float = Field(default=0.05, ge=0.0, le=1.0)
    combo_fill_bonus: float = Field(default=0.10, ge=0.0, le=1.0)


class MarginPolicy(StrictModel):
    allow_span_like: bool = True
    allow_rule_based: bool = True
    stress_loss_multiplier: float = Field(default=1.0, ge=1.0)
    settlement_reserve_rate: float = Field(default=0.02, ge=0.0)
    liquidity_addon_rate: float = Field(default=0.05, ge=0.0)


class ReconciliationPolicy(StrictModel):
    degraded_cap_multiplier: float = Field(default=0.50, ge=0.0, le=1.0)
    quantity_tolerance: float = Field(default=1e-8, ge=0.0)
    require_physical_reconciliation: bool = True
