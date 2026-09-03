"""S3: point-in-time return forecasts from qualified portable models."""
from __future__ import annotations

from typing import Any

import numpy as np

from ..domain.core import HandlerOutcome, ModuleStatus
from ..domain.distributions import ParametricDistribution, PointDistribution
from ..domain.forecast import ForecastMemberPanel, ForecastMemberRecord
from ..errors import DataQualityError, TemporalIntegrityError
from ..services.calendar import horizon_end
from ..services.identifiers import as_utc, stable_id
from ..services.modeling import get_resolver
from ..services.tabular import latest_feature_rows

_FAMILIES = {
    "P5.S3.M01": {"BASELINE", "LINEAR", "ROBUST_LINEAR"}, "P5.S3.M02": {"STATE_SPACE"},
    "P5.S3.M03": {"TREE", "KERNEL"}, "P5.S3.M04": {"TEMPORAL_NEURAL"},
    "P5.S3.M05": {"FOUNDATION"},
}


def run(module_id: str, payload: dict[str, Any], *, as_of_time) -> HandlerOutcome:
    qualified = _mapping(payload, "qualified_resolver_registry").get("records", [])
    views = {row["view_id"]: row for row in _mapping(payload, "authorized_consumer_view_registry").get("views", [])}
    models = [row for row in qualified if row.get("resolver_family") in _FAMILIES[module_id]]
    if not models:
        return HandlerOutcome(values=(), status=ModuleStatus.SKIPPED,
                              warnings=(f"no qualified resolver for families {sorted(_FAMILIES[module_id])}",))
    records = [record for model in models for record in _predict_model(module_id, model, views, as_of_time)]
    if not records:
        raise DataQualityError("qualified return resolvers produced no forecast records")
    return HandlerOutcome(values=(ForecastMemberPanel(records=tuple(records)),))


def _predict_model(module_id, model, views, as_of_time):
    view = views.get(model["feature_view_id"])
    if view is None:
        return []
    cutoff = as_utc(model["training_cutoff"])
    if cutoff > as_of_time:
        raise TemporalIntegrityError(f"model {model['resolver_id']} training_cutoff exceeds as_of_time")
    feature_names = tuple(model["feature_names"])
    imputation = np.asarray(model.get("imputation_values", []), dtype=float)
    if imputation.shape != (len(feature_names),):
        raise DataQualityError(f"model {model['resolver_id']} lacks valid imputation values")
    rows = latest_feature_rows(view, as_of_time=as_of_time, horizon=model["horizon"])
    matrix, missing = _matrix(rows, feature_names, imputation)
    predictions = get_resolver(model["implementation_id"]).predict(model["model_state"], matrix)
    return [
        _record(module_id, model, row, prediction, absent, cutoff, as_of_time)
        for row, prediction, absent in zip(rows, predictions, missing, strict=True)
    ]


def _matrix(rows, feature_names, imputation):
    matrix, missing = [], []
    for row in rows:
        values, absent = [], []
        for index, name in enumerate(feature_names):
            value = row["features"].get(name)
            if value is None:
                value = float(imputation[index]); absent.append(name)
            values.append(float(value))
        if absent and len(absent) / len(feature_names) > 0.5:
            raise DataQualityError("more than half of a model's features are missing at inference")
        matrix.append(values)
        missing.append(tuple(absent))
    return np.asarray(matrix, dtype=float), missing


def _record(module_id, model, row, prediction, missing, cutoff, as_of_time):
    if model.get("residual_std") is None:
        raise DataQualityError("trained resolver is missing residual uncertainty")
    residual_std = float(model["residual_std"])
    distribution = ParametricDistribution(family="NORMAL", location=float(prediction), scale=residual_std) if residual_std > 1e-10 else PointDistribution(value=float(prediction))
    prediction_timestamp = horizon_end(as_of_time, model["horizon"])
    return ForecastMemberRecord(
        record_id=stable_id(module_id, model["resolver_id"], row["underlying"], prediction_timestamp),
        as_of_time=as_of_time, prediction_timestamp=prediction_timestamp, underlying=row["underlying"],
        target_id=model["target_id"], horizon=model["horizon"], unit=model["unit"],
        resolver_id=model["resolver_id"], resolver_family=model["resolver_family"],
        model_artifact_id=model["model_artifact_id"], feature_view_id=model["feature_view_id"],
        training_cutoff=cutoff, lineage_id=stable_id(row["lineage_id"], model["model_artifact_id"]),
        distribution=distribution, role=model.get("role", "CHALLENGER"),
        status="DEGRADED" if missing else "VALID", metadata={
            "imputed_features": missing,
            "distribution_source": "POINT_PLUS_CALIBRATION_RESIDUAL_SCALE",
            "algorithm_version": "RC34-INTEGRATION-HARDENED",
        },
    )



def _mapping(payload: dict[str, Any], name: str) -> dict[str, Any]:
    value = payload.get(name)
    if not isinstance(value, dict):
        raise DataQualityError(f"{name} must be an object")
    return value
