import pytest

from quant_pipeline.phase_09.subphases.s07_prospective_validation.contracts import EvidenceClass
from quant_pipeline.phase_09.subphases.s08_attribution.contracts import AttributionQuality
from quant_pipeline.phase_09.subphases.s08_attribution.m01_forecast_attribution import (
    ForecastAttributionPolicy,
    ForecastComponentObservation,
    attribute_forecast_components,
)


def _row(index: int, component: str = "a", prediction: float | None = None):
    return ForecastComponentObservation(
        observation_id=f"o{index}", target_id="t", horizon_id="h", regime_id="r",
        component_id=component, component_kind="MODEL", consumed=True,
        historical_weight=1.0, ensemble_loss=0.1, ablated_loss=0.3,
        component_prediction=float(index) if prediction is None else prediction,
        oof_qualified=True, observable_pnl_with_component=1.0,
        observable_pnl_without_component=0.0,
        evidence_class=EvidenceClass.OBSERVABLE_COUNTERFACTUAL,
    )


def test_forecast_attribution_qualified():
    result = attribute_forecast_components(tuple(_row(i) for i in range(3)), ForecastAttributionPolicy())
    assert result.quality is AttributionQuality.QUALIFIED
    assert result.components[0].mean_loss_increase_when_removed == pytest.approx(0.2)
    assert result.aggregate_pnl_effect == 3.0


def test_forecast_oof_missing_is_limited():
    rows = [_row(i) for i in range(3)]
    rows[0] = rows[0].model_copy(update={"oof_qualified": False})
    result = attribute_forecast_components(tuple(rows), ForecastAttributionPolicy())
    assert result.quality is AttributionQuality.LIMITED
    assert "P9_ATTRIBUTION_COMPONENT_OOF_MISSING" in result.reason_codes


def test_unconsumed_component_gets_no_credit():
    rows = tuple(
        _row(i).model_copy(update={"consumed": False, "historical_weight": 0.0})
        for i in range(3)
    )
    result = attribute_forecast_components(rows, ForecastAttributionPolicy())
    assert result.components[0].aggregate_pnl_effect is None
    assert result.quality is AttributionQuality.INSUFFICIENT_EVIDENCE


def test_collinearity_is_reported():
    rows = tuple(_row(i, "a") for i in range(3)) + tuple(_row(i, "b") for i in range(3))
    result = attribute_forecast_components(rows, ForecastAttributionPolicy(collinearity_threshold=0.9))
    assert len(result.collinearity_pairs) == 1
    assert "P9_ATTRIBUTION_VIEW_COLLINEARITY_UNRESOLVED" in result.reason_codes
