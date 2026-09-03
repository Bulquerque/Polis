"""S4: forecast-conditional volatility and path-risk members."""
from __future__ import annotations

from typing import Any

import numpy as np

from ..domain.core import HandlerOutcome, ModuleStatus
from ..domain.distributions import PointDistribution
from ..domain.forecast import ForecastMemberPanel, ForecastMemberRecord
from ..errors import CapabilityUnavailableError, DataQualityError
from ..services.feature_semantics import first_available
from ..services.calendar import horizon_end
from ..services.identifiers import stable_id
from ..services.oof_evidence import predictive_series, residual_series
from ..services.risk import ewma_variance, gjr_variance, har_variance, implied_blend, path_risk
from ..services.tabular import latest_feature_rows


def m01(payload: dict[str, Any], *, as_of_time) -> HandlerOutcome:
    model, series, cutoff = _residual_evidence(payload)
    records = []
    for underlying, values in series.items():
        variance, diagnostics = har_variance(values)
        for horizon, sessions in (("1D", 1), ("5D", 5)):
            records.append(_risk_record(
                module="P5.S4.M01", model=model, underlying=underlying,
                target_id=f"volatility_{horizon.lower()}",
                value=float(np.sqrt(variance * sessions)),
                resolver="log-har-oof-residual", family="VOLATILITY_HAR",
                unit="decimal_volatility", cutoff=cutoff, as_of_time=as_of_time,
                horizon=horizon,
                metadata={
                    **diagnostics,
                    "conditioning": "RETURN_FORECAST_OOF_RESIDUAL",
                    "horizon_scaling": "SQUARE_ROOT_TIME_BASELINE" if sessions > 1 else "ONE_STEP",
                },
            ))
    return HandlerOutcome(values=(_panel(records),))


def m02(payload: dict[str, Any], *, as_of_time) -> HandlerOutcome:
    model, series, cutoff = _residual_evidence(payload)
    records: list[ForecastMemberRecord] = []
    for underlying, values in series.items():
        variance, diagnostics = gjr_variance(values)
        records.append(_risk_record(
            module="P5.S4.M02", model=model, underlying=underlying,
            target_id="conditional_volatility_1d", value=float(np.sqrt(variance)),
            resolver="gjr-garch-oof-residual", family="CONDITIONAL_VOLATILITY",
            unit="decimal_volatility", cutoff=cutoff, as_of_time=as_of_time,
            metadata={**diagnostics, "conditioning": "RETURN_FORECAST_OOF_RESIDUAL"},
        ))
    return HandlerOutcome(values=(_panel(records),))


def m03(payload: dict[str, Any], *, as_of_time) -> HandlerOutcome:
    model, series, cutoff = _residual_evidence(payload)
    view = _view(payload, "TABULAR_INTERPRETABLE")
    rows = latest_feature_rows(view, as_of_time=as_of_time, horizon="1D")
    records: list[ForecastMemberRecord] = []
    for row in rows:
        implied_name = first_available("implied_volatility_state", row["features"])
        if implied_name != "options.atm_implied_volatility":
            continue
        implied = row["features"].get(implied_name)
        values = series.get(row["underlying"])
        if implied is None or values is None:
            continue
        count = row["features"].get("options.coverage_count")
        if count is None:
            continue
        coverage = min(max(float(count) / 5.0, 0.05), 1.0)
        variance, diagnostics = implied_blend(
            ewma_variance(values),
            {"implied_volatility": float(implied), "coverage": coverage},
        )
        records.append(_risk_record(
            module="P5.S4.M03", model=model, underlying=row["underlying"],
            target_id="realized_implied_volatility_1d", value=float(np.sqrt(variance)),
            resolver="realized-implied-oof-blend", family="OPTION_IMPLIED_VOLATILITY",
            unit="decimal_volatility", cutoff=cutoff, as_of_time=as_of_time,
            metadata={
                **diagnostics,
                "implied_feature_id": implied_name,
                "coverage_feature_id": "options.coverage_count",
                "conditioning": "RETURN_FORECAST_OOF_RESIDUAL",
            },
        ))
    if not records:
        return HandlerOutcome(
            values=(), status=ModuleStatus.SKIPPED,
            warnings=("P4 V14.9 did not authorize a usable option-implied volatility feature",),
        )
    return HandlerOutcome(values=(_panel(records),))


def m04(payload: dict[str, Any], *, as_of_time) -> HandlerOutcome:
    qualified = payload.get("qualified_resolver_registry", {}).get("records", [])
    models = [
        row for row in qualified
        if row.get("resolver_family") in {"VOLATILITY_ML", "VOLATILITY_NEURAL"}
    ]
    if not models:
        return HandlerOutcome(
            values=(), status=ModuleStatus.SKIPPED,
            warnings=("no qualified canonical ML/neural volatility resolver",),
        )
    raise CapabilityUnavailableError(
        "qualified ML volatility models require an installed canonical adapter"
    )


def m05(payload: dict[str, Any], *, as_of_time) -> HandlerOutcome:
    model, samples, _, cutoff = predictive_series(payload)
    records: list[ForecastMemberRecord] = []
    for underlying, values in samples.items():
        metrics = path_risk(values)
        for target_id, value in metrics.items():
            records.append(_risk_record(
                module="P5.S4.M05", model=model, underlying=underlying,
                target_id=target_id, value=value,
                resolver="predictive-path-risk", family="PATH_RISK",
                unit=_path_unit(target_id), cutoff=cutoff, as_of_time=as_of_time,
                metadata={
                    "sample_size": len(values),
                    "conditioning": "CURRENT_RETURN_FORECAST_PLUS_OOF_RESIDUAL",
                },
            ))
    return HandlerOutcome(
        values=(_panel(records),), status=ModuleStatus.DEGRADED,
        warnings=("liquidity stress unavailable: no qualified liquidity series was supplied",),
    )


def _residual_evidence(payload):
    return residual_series(
        payload.get("oof_validation_observation_panel"),
        _mapping(payload, "qualified_resolver_registry"),
    )


def _risk_record(
    *, module, model, underlying, target_id, value, resolver, family,
    unit, cutoff, as_of_time, metadata, horizon="1D",
):
    enriched = {
        **metadata,
        "source_return_resolver_id": model["resolver_id"],
        "source_return_model_artifact_id": model["model_artifact_id"],
        "algorithm_version": "RC34-INTEGRATION-HARDENED-P4-V14.9-NATIVE",
        "evidence_cutoff": cutoff.isoformat(),
    }
    return ForecastMemberRecord(
        record_id=stable_id(module, model["resolver_id"], underlying, target_id, as_of_time),
        as_of_time=as_of_time,
        prediction_timestamp=horizon_end(as_of_time, horizon),
        underlying=underlying,
        target_id=target_id,
        horizon=horizon,
        unit=unit,
        resolver_id=resolver,
        resolver_family=family,
        model_artifact_id=stable_id(
            "derived-risk-model", module, model["model_artifact_id"], cutoff, enriched,
        ),
        feature_view_id=model["feature_view_id"],
        training_cutoff=cutoff,
        lineage_id=stable_id("risk-lineage", module, model["model_artifact_id"], underlying, cutoff),
        distribution=PointDistribution(value=float(value)),
        role="CHALLENGER",
        metadata=enriched,
    )


def _view(payload: dict[str, Any], view_id: str) -> dict[str, Any]:
    registry = _mapping(payload, "authorized_consumer_view_registry")
    views = {row["view_id"]: row for row in registry.get("views", [])}
    if view_id not in views:
        raise DataQualityError(f"P4 consumer view {view_id} is unavailable")
    return views[view_id]


def _mapping(payload: dict[str, Any], name: str) -> dict[str, Any]:
    value = payload.get(name)
    if not isinstance(value, dict):
        raise DataQualityError(f"{name} must be an object")
    return value


def _panel(records):
    if not records:
        raise DataQualityError("risk resolver produced no records")
    return ForecastMemberPanel(records=tuple(records))


def _path_unit(target_id: str) -> str:
    if target_id in {"jump_probability", "gap_probability"}:
        return "probability"
    if target_id == "liquidity_risk":
        return "liquidity_stress"
    return "positive_loss"
