"""S7: regime, rupture, disaggregated OOD, disagreement and context routing."""
from __future__ import annotations

from typing import Any

import numpy as np

from ..domain.core import HandlerOutcome
from ..domain.forecast import ForecastMemberPanel, OOFValidationObservationPanel
from ..errors import CapabilityUnavailableError, DataQualityError, TemporalIntegrityError
from ..services.diagnostics import disagreement, ood_score, page_hinkley, recurrent_regime, route_context
from ..services.feature_semantics import aliases
from ..services.identifiers import as_utc, stable_id
from ..services.tabular import feature_rows, latest_feature_rows, merge_horizon_rows, multivariate_series, simple_return_matrix


def m01(payload: dict[str, Any], *, as_of_time) -> HandlerOutcome:
    view = _view(payload, ("REGIME_CONTEXT", "SEQUENCE_MULTI_HORIZON", "TABULAR_INTERPRETABLE"))
    records = []
    try:
        _, entities, matrix = simple_return_matrix(view, as_of_time=as_of_time)
        for column, underlying in enumerate(entities):
            result = recurrent_regime(matrix[:, column])
            records.append({
                "underlying": underlying,
                "horizon": "1D",
                "as_of_time": as_of_time.isoformat(),
                "feature_view_id": view["view_id"],
                "lineage_id": stable_id("regime", view.get("lineage_id"), underlying, result),
                "sample_size": len(matrix),
                **result,
            })
        aggregate = recurrent_regime(np.mean(matrix, axis=1))
    except CapabilityUnavailableError:
        values = _aggregate_series(view, as_of_time=as_of_time)
        aggregate = recurrent_regime(values)
        records.append({
            "underlying": "MARKET_AGGREGATE", "horizon": "1D",
            "as_of_time": as_of_time.isoformat(), "feature_view_id": view["view_id"],
            "lineage_id": stable_id("regime", view.get("lineage_id"), aggregate),
            "sample_size": len(values), **aggregate,
        })
    return HandlerOutcome(values=({
        **aggregate,
        "records": records,
        "as_of_time": as_of_time.isoformat(),
        "feature_view_id": view["view_id"],
        "lineage_id": stable_id("regime-panel", [row["lineage_id"] for row in records]),
        "method": "THRESHOLD_BASELINE_PLUS_GAUSSIAN_HMM_CHALLENGER",
    },))


def m02(payload: dict[str, Any], *, as_of_time) -> HandlerOutcome:
    view = _view(payload, ("REGIME_CONTEXT", "SEQUENCE_MULTI_HORIZON", "TABULAR_INTERPRETABLE"))
    values = _aggregate_series(view, as_of_time=as_of_time)
    result = page_hinkley(values)
    result.update({
        "as_of_time": as_of_time.isoformat(),
        "feature_view_id": view["view_id"],
        "lineage_id": stable_id("change-point", view.get("lineage_id"), result),
        "sample_size": len(values),
    })
    return HandlerOutcome(values=(result,))


def m03(payload: dict[str, Any], *, as_of_time) -> HandlerOutcome:
    registry = payload.get("authorized_consumer_view_registry", {})
    views = {row["view_id"]: row for row in registry.get("views", [])}
    qualified = payload.get("qualified_resolver_registry", {}).get("records", [])
    if not qualified:
        raise DataQualityError("resolver-specific OOD requires qualified resolvers")
    dependence_ood = _dependence_ood(payload.get("covariance_forecast_registry"))
    records: list[dict[str, Any]] = []
    for model in qualified:
        view_id = str(model.get("feature_view_id", ""))
        view = views.get(view_id)
        if view is None:
            records.append(_unavailable_ood_record(
                model, as_of_time, "P5_OOD_FEATURE_VIEW_UNAVAILABLE",
                f"authorized feature view {view_id!r} is unavailable",
            ))
            continue
        try:
            model_records = _model_ood_records(model, view, as_of_time, dependence_ood)
        except TemporalIntegrityError:
            raise
        except DataQualityError as exc:
            records.append(_unavailable_ood_record(
                model, as_of_time, "P5_OOD_REFERENCE_INVALID", str(exc),
            ))
            continue
        if model_records:
            records.extend(model_records)
        else:
            records.append(_unavailable_ood_record(
                model, as_of_time, "P5_OOD_CURRENT_VIEW_EMPTY",
                "no current rows were available for the resolver scope",
            ))
    if not records:
        raise DataQualityError("resolver-specific OOD produced no resolver receipts")
    return HandlerOutcome(values=({
        "records": records,
        "resolver_count": len(qualified),
        "available_count": sum(row.get("availability_status") == "AVAILABLE" for row in records),
        "unavailable_count": sum(row.get("availability_status") != "AVAILABLE" for row in records),
        "component_semantics": {
            "feature_ood": "EMPIRICAL_MAHALANOBIS_TAIL_SCORE",
            "representation_ood": "MAX_STANDARDIZED_FEATURE_SHIFT",
            "model_ood": "FOLD_STABILITY_DERIVED_OR_UNAVAILABLE",
            "market_state_ood": "FEATURE_AND_REPRESENTATION_AGGREGATE",
            "dependence_ood": "CHAMPION_COVARIANCE_STABILITY_OR_UNAVAILABLE",
        },
    },))


def m04(payload: dict[str, Any]) -> HandlerOutcome:
    panels = [
        ForecastMemberPanel.model_validate(value)
        for name, value in payload.items()
        if name.startswith((
            "return_member_", "volatility_member_", "path_risk_member_",
            "tail_member_", "scenario_member_",
        )) and isinstance(value, dict)
    ]
    perspective = payload.get("p4_perspective_context")
    observations = payload.get("oof_validation_observation_panel")
    oof = OOFValidationObservationPanel.model_validate(observations) if isinstance(observations, dict) else None
    return HandlerOutcome(values=(disagreement(panels, perspective, oof),))


def m05(payload: dict[str, Any]) -> HandlerOutcome:
    return HandlerOutcome(values=route_context(
        _mapping(payload, "regime_probability_member_panel"),
        _mapping(payload, "structural_break_member_panel"),
        _mapping(payload, "ood_drift_diagnostics_panel"),
        _mapping(payload, "perspective_model_disagreement_panel"),
    ))


def _model_ood_records(model, view, as_of_time, dependence_ood):
    cutoff = as_utc(model["training_cutoff"])
    if cutoff > as_of_time:
        raise TemporalIntegrityError(f"OOD model {model['resolver_id']} has future training cutoff")
    names = tuple(model.get("feature_names", ()))
    imputation = np.asarray(model.get("imputation_values", ()), dtype=float)
    if not names or imputation.shape != (len(names),):
        raise DataQualityError(f"OOD model {model['resolver_id']} lacks training feature profile")
    horizon = str(model["horizon"])
    reference_rows = merge_horizon_rows(feature_rows(view, as_of_time=cutoff), horizon=horizon)
    current_rows = latest_feature_rows(view, as_of_time=as_of_time, horizon=horizon)
    output = []
    for row in current_rows:
        entity_rows = [candidate for candidate in reference_rows if candidate.get("underlying") == row.get("underlying")]
        reference = np.asarray([_vector(candidate, names, imputation) for candidate in entity_rows], dtype=float)
        minimum_reference = max(30, 5 * len(names))
        if len(reference) < minimum_reference:
            raise DataQualityError(
                f"OOD reference too small for {model['resolver_id']} / {row['underlying']}: "
                f"requires {minimum_reference}, observed {len(reference)}"
            )
        diagnostics = ood_score(reference, _vector(row, names, imputation))
        model_score = _model_stability_ood(model)
        representation = float(np.clip(diagnostics["maximum_standardized_shift"] / 5.0, 0.0, 1.0))
        market = float(np.mean([diagnostics["ood_score"], representation]))
        available = [diagnostics["ood_score"], representation, market]
        if model_score is not None: available.append(model_score)
        if dependence_ood is not None: available.append(dependence_ood)
        output.append({
            **diagnostics,
            "resolver_id": model["resolver_id"],
            "underlying": row["underlying"],
            "horizon": horizon,
            "feature_view_id": view["view_id"],
            "feature_names": names,
            "training_cutoff": cutoff.isoformat(),
            "as_of_time": as_of_time.isoformat(),
            "feature_ood": diagnostics["ood_score"],
            "representation_ood": representation,
            "model_ood": model_score,
            "model_ood_status": "AVAILABLE" if model_score is not None else "UNAVAILABLE",
            "market_state_ood": market,
            "dependence_ood": dependence_ood,
            "dependence_ood_status": "AVAILABLE" if dependence_ood is not None else "UNAVAILABLE",
            "overall_ood": float(max(available)),
            "availability_status": "AVAILABLE",
            "reason_code": None,
            "reference_minimum_required": minimum_reference,
            "reference_sample_size": len(reference),
        })
    return output


def _unavailable_ood_record(model, as_of_time, reason_code, message):
    return {
        "resolver_id": str(model.get("resolver_id", "UNKNOWN")),
        "underlying": str(model.get("underlying", "UNAVAILABLE")),
        "horizon": str(model.get("horizon", "UNAVAILABLE")),
        "feature_view_id": model.get("feature_view_id"),
        "training_cutoff": str(model.get("training_cutoff", "")),
        "as_of_time": as_of_time.isoformat(),
        "feature_ood": None,
        "representation_ood": None,
        "model_ood": None,
        "market_state_ood": None,
        "dependence_ood": None,
        "overall_ood": None,
        "availability_status": "UNAVAILABLE",
        "reason_code": reason_code,
        "diagnostic_message": message,
    }


def _vector(row: dict[str, Any], names: tuple[str, ...], imputation: np.ndarray) -> np.ndarray:
    return np.asarray([
        float(imputation[index]) if row["features"].get(name) is None else float(row["features"][name])
        for index, name in enumerate(names)
    ], dtype=float)


def _model_stability_ood(model: dict[str, Any]) -> float | None:
    stability = model.get("fold_stability") or model.get("validation_stability")
    if stability is None:
        return None
    value = float(stability)
    if not np.isfinite(value):
        return None
    return float(np.clip(1.0 - value, 0.0, 1.0))


def _dependence_ood(registry: Any) -> float | None:
    if not isinstance(registry, dict):
        return None
    champion = registry.get("champion_registry_id")
    records = [row for row in registry.get("records", []) if row.get("registry_id") == champion]
    if not records:
        return None
    stability = records[0].get("stability", {})
    late = stability.get("candidate_late_frobenius")
    early = stability.get("early_late_frobenius")
    if late is None or early is None:
        return None
    return float(np.clip(float(late) / max(float(early), 1e-8), 0.0, 1.0))


def _view(payload: dict[str, Any], candidates: tuple[str, ...]) -> dict[str, Any]:
    registry = payload.get("authorized_consumer_view_registry", {})
    views = {row["view_id"]: row for row in registry.get("views", [])}
    for candidate in candidates:
        if candidate in views:
            return views[candidate]
    raise DataQualityError(f"none of the diagnostic views are available: {candidates}")


def _aggregate_series(view: dict[str, Any], *, as_of_time) -> np.ndarray:
    try:
        _, _, matrix = simple_return_matrix(view, as_of_time=as_of_time)
        return np.mean(matrix, axis=1)
    except CapabilityUnavailableError:
        for feature in (*aliases("regime_state"), "market_state"):
            try:
                _, matrix = multivariate_series(view, feature, as_of_time=as_of_time)
                return np.mean(matrix, axis=1)
            except DataQualityError:
                continue
        raise DataQualityError("diagnostic view contains no aligned supported time series")


def _mapping(payload: dict[str, Any], name: str) -> dict[str, Any]:
    value = payload.get(name)
    if not isinstance(value, dict):
        raise DataQualityError(f"{name} must be an object")
    return value
