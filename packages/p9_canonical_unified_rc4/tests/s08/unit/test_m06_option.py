from datetime import UTC, datetime, timedelta
import pytest

from quant_pipeline.phase_09.subphases.s08_attribution.contracts import AttributionQuality
from quant_pipeline.phase_09.subphases.s08_attribution.m06_option_attribution import OptionAttributionInterval, OptionAttributionPolicy, attribute_option_pnl

NOW=datetime(2026,1,1,tzinfo=UTC)


def _interval(**updates):
    base=dict(position_id="p", interval_start=NOW, interval_end=NOW+timedelta(days=1), greek_snapshot_time=NOW, quantity=1.0, price_before=10.0, price_after=11.0, delta=1.0, gamma=0.0, vega=0.0, theta_per_year=0.0, rho=0.0, spot_change=1.0, volatility_change=0.0, year_fraction=0.0, rate_change=0.0)
    base.update(updates)
    return OptionAttributionInterval(**base)


def test_exact_delta_explanation():
    result=attribute_option_pnl((_interval(),), OptionAttributionPolicy())
    assert result.full_repricing_pnl == 1.0
    assert result.residual_pnl == 0.0
    assert result.quality is AttributionQuality.QUALIFIED


def test_gamma_and_vega_components():
    item=_interval(price_after=12.5, delta=1.0, gamma=1.0, vega=10.0, spot_change=1.0, volatility_change=0.1)
    result=attribute_option_pnl((item,), OptionAttributionPolicy())
    interval=result.intervals[0]
    assert interval.gamma_pnl == 0.5
    assert interval.vega_pnl == 1.0
    assert interval.residual_pnl == 0.0


def test_material_residual_is_limited():
    result=attribute_option_pnl((_interval(price_after=12.0),), OptionAttributionPolicy(residual_tolerance=0.1))
    assert result.quality is AttributionQuality.LIMITED
    assert "P9_ATTRIBUTION_OPTION_RESIDUAL_MATERIAL" in result.reason_codes


def test_missing_surface_is_limited():
    result=attribute_option_pnl((_interval(surface_available=False),), OptionAttributionPolicy(require_surface=True))
    assert "P9_ATTRIBUTION_VOL_SURFACE_UNAVAILABLE" in result.reason_codes


def test_greek_snapshot_after_move_rejected():
    with pytest.raises(ValueError):
        _interval(greek_snapshot_time=NOW+timedelta(seconds=1))
