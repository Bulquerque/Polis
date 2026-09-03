"""S8: harmonization, scoring, conformal calibration, pruning and ensemble."""
from __future__ import annotations

from typing import Any

from ..domain.core import HandlerOutcome
from ..domain.forecast import ForecastMemberPanel, OOFValidationObservationPanel
from ..errors import DataQualityError
from ..services import ensemble


def m01(payload: dict[str, Any]) -> HandlerOutcome:
    panels: list[ForecastMemberPanel] = []
    for name, value in payload.items():
        if name.startswith(("return_member_", "volatility_member_", "path_risk_member_")) and isinstance(value, dict):
            panels.append(ForecastMemberPanel.model_validate(value))
    validated = payload.get("validated_tail_scenario_registry")
    if isinstance(validated, dict) and validated.get("records"):
        panels.append(ForecastMemberPanel.model_validate({"records": validated["records"]}))
    return HandlerOutcome(values=(ensemble.harmonize(panels),))


def m02(payload: dict[str, Any]) -> HandlerOutcome:
    panel = ForecastMemberPanel.model_validate(_mapping(payload, "harmonized_forecast_member_panel"))
    observations = OOFValidationObservationPanel.model_validate(
        _mapping(payload, "oof_validation_observation_panel")
    )
    return HandlerOutcome(values=ensemble.score(panel, observations))


def m03(payload: dict[str, Any]) -> HandlerOutcome:
    panel = ForecastMemberPanel.model_validate(_mapping(payload, "harmonized_forecast_member_panel"))
    diagnostics = _mapping(payload, "forecast_calibration_diagnostics")
    router = payload.get("resolver_context_router_panel")
    return HandlerOutcome(values=ensemble.calibrate(panel, diagnostics, router))


def m04(payload: dict[str, Any]) -> HandlerOutcome:
    panel = ForecastMemberPanel.model_validate(_mapping(payload, "calibrated_forecast_member_panel"))
    scoring = _mapping(payload, "forecast_scoring_panel")
    maximum = int(payload.get("max_candidates", 5))
    if not 1 <= maximum <= 8:
        raise DataQualityError("max_candidates must be between one and eight")
    observations = payload.get("oof_validation_observation_panel")
    oof = OOFValidationObservationPanel.model_validate(observations) if isinstance(observations, dict) else None
    return HandlerOutcome(values=ensemble.prune(panel, scoring, maximum, oof))


def m05(payload: dict[str, Any]) -> HandlerOutcome:
    panel = ForecastMemberPanel.model_validate(_mapping(payload, "calibrated_forecast_member_panel"))
    candidates = _mapping(payload, "ensemble_candidate_panel")
    scoring = _mapping(payload, "forecast_scoring_panel")
    router = payload.get("resolver_context_router_panel")
    maximum = int(payload.get("max_members", 3))
    if not 1 <= maximum <= 3:
        raise DataQualityError("productive ensemble max_members must be between one and three")
    floor = float(payload.get("confidence_floor", 0.20))
    if not 0.0 <= floor <= 1.0:
        raise DataQualityError("confidence_floor must be between zero and one")
    observations = payload.get("oof_validation_observation_panel")
    oof = OOFValidationObservationPanel.model_validate(observations) if isinstance(observations, dict) else None
    return HandlerOutcome(values=ensemble.build_ensemble(
        panel,
        candidates,
        scoring,
        router,
        oof,
        max_members=maximum,
        confidence_floor=floor,
    ))


def _mapping(payload: dict[str, Any], name: str) -> dict[str, Any]:
    value = payload.get(name)
    if not isinstance(value, dict):
        raise DataQualityError(f"{name} must be an object")
    return value
