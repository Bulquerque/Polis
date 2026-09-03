"""Out-of-fold evidence readers for runtime risk, tail and dependence modules."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

import numpy as np

from ..domain.forecast import ForecastMemberPanel, OOFValidationObservationPanel
from ..errors import DataQualityError
from .identifiers import as_utc

_FAMILY_PRIORITY = {
    "LINEAR": 0,
    "STATE_SPACE": 1,
    "TREE": 2,
    "BASELINE": 3,
}


def qualified_candidates(
    qualified_registry: dict[str, Any], *, target_id: str, horizon: str,
) -> tuple[dict[str, Any], ...]:
    candidates = [
        row for row in qualified_registry.get("records", [])
        if row.get("target_id") == target_id and row.get("horizon") == horizon
    ]
    return tuple(sorted(
        candidates,
        key=lambda row: (
            _FAMILY_PRIORITY.get(str(row.get("resolver_family")), 99),
            float(row.get("metrics", {}).get("mse", float("inf"))),
            str(row.get("resolver_id")),
        ),
    ))


def selected_resolver(
    qualified_registry: dict[str, Any], *, target_id: str, horizon: str,
) -> dict[str, Any]:
    candidates = qualified_candidates(
        qualified_registry, target_id=target_id, horizon=horizon,
    )
    if not candidates:
        raise DataQualityError(f"no qualified resolver for {target_id}/{horizon}")
    return candidates[0]


def residual_series(
    oof_value: Any,
    qualified_registry: dict[str, Any],
    *,
    target_id: str = "excess_return_1d",
    horizon: str = "1D",
    resolver_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, np.ndarray], datetime]:
    candidates = qualified_candidates(
        qualified_registry, target_id=target_id, horizon=horizon,
    )
    if resolver_id is not None:
        candidates = tuple(row for row in candidates if row.get("resolver_id") == resolver_id)
    if not candidates:
        raise DataQualityError(f"no qualified resolver for {target_id}/{horizon}")
    panel = _oof_panel(oof_value)
    for model in candidates:
        grouped = _residual_groups(panel, model["resolver_id"], target_id, horizon)
        series = {
            entity: np.asarray([value for _, value in sorted(values)], dtype=float)
            for entity, values in grouped.items() if len(values) >= 8
        }
        if series:
            cutoff = max(time for values in grouped.values() for time, _ in values)
            return model, series, as_utc(cutoff)
    raise DataQualityError("qualified resolvers have insufficient OOF residual evidence")


def predictive_series(
    payload: dict[str, Any],
    *,
    target_id: str = "excess_return_1d",
    horizon: str = "1D",
) -> tuple[dict[str, Any], dict[str, np.ndarray], dict[str, float], datetime]:
    qualified = _mapping(payload, "qualified_resolver_registry")
    oof = payload.get("oof_validation_observation_panel")
    points = current_point_forecasts(payload)
    for model in qualified_candidates(qualified, target_id=target_id, horizon=horizon):
        resolver_id = str(model["resolver_id"])
        centers = {
            underlying: value
            for (resolver, underlying, target, member_horizon), value in points.items()
            if resolver == resolver_id and target == target_id and member_horizon == horizon
        }
        if not centers:
            continue
        try:
            _, residuals, cutoff = residual_series(
                oof,
                qualified,
                target_id=target_id,
                horizon=horizon,
                resolver_id=resolver_id,
            )
        except DataQualityError:
            continue
        common = sorted(set(centers) & set(residuals))
        if common:
            samples = {
                entity: residuals[entity] + float(centers[entity])
                for entity in common
            }
            return model, samples, {entity: centers[entity] for entity in common}, cutoff
    raise DataQualityError("no qualified current return forecast has matching OOF evidence")


def active_target_horizon(payload: dict[str, Any], *, require_current: bool = True) -> tuple[str, str]:
    """Return the current qualified target/horizon shared by forecasts and OOF evidence."""
    qualified = _mapping(payload, "qualified_resolver_registry")
    points = current_point_forecasts(payload)
    panel = _oof_panel(payload.get("oof_validation_observation_panel"))
    qualified_pairs = sorted({
        (str(row.get("target_id")), str(row.get("horizon")))
        for row in qualified.get("records", [])
    })
    for target_id, horizon in qualified_pairs:
        for model in qualified_candidates(qualified, target_id=target_id, horizon=horizon):
            resolver_id = str(model["resolver_id"])
            has_current = any(
                resolver == resolver_id and target == target_id and member_horizon == horizon
                for resolver, _underlying, target, member_horizon in points
            )
            if (not require_current or has_current) and sum(
                row.resolver_id == resolver_id
                and row.target_id == target_id
                and row.horizon == horizon
                for row in panel.records
            ) >= 8:
                return target_id, horizon
    raise DataQualityError("no active target/horizon has current forecast and OOF evidence")


def residual_matrix(
    oof_value: Any,
    qualified_registry: dict[str, Any],
    *,
    target_id: str = "excess_return_1d",
    horizon: str = "1D",
) -> tuple[dict[str, Any], tuple[str, ...], np.ndarray, datetime]:
    panel = _oof_panel(oof_value)
    for model in qualified_candidates(
        qualified_registry, target_id=target_id, horizon=horizon,
    ):
        rows = [
            row for row in panel.records
            if row.resolver_id == model["resolver_id"]
            and row.target_id == target_id
            and row.horizon == horizon
        ]
        entities = tuple(sorted({row.underlying for row in rows}))
        times = sorted({row.prediction_timestamp for row in rows})
        mapping = {
            (row.prediction_timestamp, row.underlying): row.realized - row.prediction
            for row in rows
        }
        matrix = np.asarray([
            [mapping.get((time, entity), np.nan) for entity in entities]
            for time in times
        ], dtype=float)
        matrix = matrix[np.all(np.isfinite(matrix), axis=1)]
        if matrix.shape[0] >= 8 and matrix.shape[1] >= 2:
            return model, entities, matrix, as_utc(max(times))
    raise DataQualityError("OOF residual covariance requires eight aligned rows and two entities")


def current_point_forecasts(payload: dict[str, Any]) -> dict[tuple[str, str, str, str], float]:
    output: dict[tuple[str, str, str, str], float] = {}
    for name, value in payload.items():
        if not name.startswith("return_member_forecast_panel_") or not isinstance(value, dict):
            continue
        panel = ForecastMemberPanel.model_validate(value)
        for row in panel.records:
            key = (row.resolver_id, row.underlying, row.target_id, row.horizon)
            if key in output:
                raise DataQualityError(f"duplicate current return forecast key: {key}")
            output[key] = row.point_forecast
    return output


def _residual_groups(panel, resolver_id, target_id, horizon):
    grouped: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    for row in panel.records:
        if row.resolver_id != resolver_id or row.target_id != target_id or row.horizon != horizon:
            continue
        grouped[row.underlying].append((row.prediction_timestamp, row.realized - row.prediction))
    return grouped


def _oof_panel(value: Any) -> OOFValidationObservationPanel:
    if isinstance(value, OOFValidationObservationPanel):
        return value
    if not isinstance(value, dict):
        raise DataQualityError("oof_validation_observation_panel is required")
    return OOFValidationObservationPanel.model_validate(value)


def _mapping(payload: dict[str, Any], name: str) -> dict[str, Any]:
    value = payload.get(name)
    if not isinstance(value, dict):
        raise DataQualityError(f"{name} must be an object")
    return value
