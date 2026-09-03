"""S5: predictive tails, calibrated block bootstrap and joint scenario paths."""
from __future__ import annotations

from typing import Any

import numpy as np

from ..domain.core import HandlerOutcome
from ..domain.distributions import PointDistribution, ScenarioDistribution, ScenarioPoint
from ..domain.forecast import ForecastMemberPanel, ForecastMemberRecord
from ..errors import DataQualityError
from ..services.calendar import horizon_end
from ..services.identifiers import stable_id
from ..services.marginal_models import conditional_quantiles, evt_diagnostics, heavy_tail_candidates
from ..services.oof_evidence import active_target_horizon, predictive_series, residual_matrix
from ..services.risk import validate_distribution_set
from ..services.scenario_engine import joint_path_bundle, univariate_path_bundle, validate_scenario_bundle


def m01(payload: dict[str, Any], *, as_of_time) -> HandlerOutcome:
    target_id, horizon = active_target_horizon(payload)
    model, samples, _, cutoff = predictive_series(payload, target_id=target_id, horizon=horizon)
    records = []
    for underlying, values in samples.items():
        distribution, diagnostics = conditional_quantiles(values)
        records.append(_record(
            module="P5.S5.M01", model=model, underlying=underlying,
            target_id="return_quantiles_1d", distribution=distribution,
            as_of_time=as_of_time, cutoff=cutoff,
            resolver="caviar-regime-conditional-quantiles", family="CONDITIONAL_QUANTILE",
            metadata={"sample_size": len(values), **diagnostics},
        ))
    return HandlerOutcome(values=(_panel(records),))


def m02(payload: dict[str, Any], *, as_of_time) -> HandlerOutcome:
    target_id, horizon = active_target_horizon(payload)
    model, samples, _, cutoff = predictive_series(payload, target_id=target_id, horizon=horizon)
    records: list[ForecastMemberRecord] = []
    for underlying, values in samples.items():
        tail = evt_diagnostics(values)
        for target_id, value in (
            ("loss_var_95", tail["var"]),
            ("loss_expected_shortfall_95", tail["expected_shortfall"]),
        ):
            records.append(_record(
                module="P5.S5.M02", model=model, underlying=underlying,
                target_id=target_id, distribution=PointDistribution(value=float(value)),
                as_of_time=as_of_time, cutoff=cutoff,
                resolver="pot-gpd-predictive", family="EXTREME_VALUE",
                metadata=tail, unit="positive_loss",
            ))
    return HandlerOutcome(values=(_panel(records),))


def m03(payload: dict[str, Any], *, as_of_time) -> HandlerOutcome:
    target_id, horizon = active_target_horizon(payload)
    model, samples, _, cutoff = predictive_series(payload, target_id=target_id, horizon=horizon)
    records: list[ForecastMemberRecord] = []
    for underlying, values in samples.items():
        for name, distribution, diagnostics in heavy_tail_candidates(values):
            records.append(_record(
                module="P5.S5.M03", model=model, underlying=underlying,
                target_id="return_distribution_1d", distribution=distribution,
                as_of_time=as_of_time, cutoff=cutoff,
                resolver=f"{name}-predictive", family="HEAVY_TAIL",
                metadata={"sample_size": len(values), **diagnostics},
            ))
    return HandlerOutcome(values=(_panel(records),))


def m04(payload: dict[str, Any], *, as_of_time, seed: int) -> HandlerOutcome:
    target_id, horizon = active_target_horizon(payload)
    model, samples, _, cutoff = predictive_series(payload, target_id=target_id, horizon=horizon)
    records: list[ForecastMemberRecord] = []
    for offset, (underlying, values) in enumerate(sorted(samples.items())):
        bundle = univariate_path_bundle(values, seed=seed + offset)
        terminal = _cumulative_terminal(np.asarray(bundle["nominal_paths"], dtype=float))
        records.append(_record(
            module="P5.S5.M04", model=model, underlying=underlying,
            target_id="return_path_5d", distribution=_scenario_distribution(terminal, "bootstrap"),
            as_of_time=as_of_time, cutoff=cutoff,
            resolver="calibrated-block-bootstrap-paths", family="MULTIPLE_FUTURE",
            horizon="5D", metadata={
                "sample_size": len(values), "scenario_bundle": bundle,
                "generator_scope": "UNIVARIATE_PATH",
            },
        ))
    return HandlerOutcome(values=(_panel(records),))


def m05(payload: dict[str, Any], *, as_of_time, seed: int) -> HandlerOutcome:
    target_id, horizon = active_target_horizon(payload)
    model, entities, residuals, cutoff = residual_matrix(
        payload.get("oof_validation_observation_panel"),
        _mapping(payload, "qualified_resolver_registry"),
        target_id=target_id, horizon=horizon,
    )
    _, _, centers, _ = predictive_series(payload, target_id=target_id, horizon=horizon)
    common = tuple(entity for entity in entities if entity in centers)
    if len(common) < 2:
        raise DataQualityError("joint scenarios require current forecasts for two underlyings")
    positions = [entities.index(entity) for entity in common]
    matrix = residuals[:, positions]
    center = np.asarray([centers[entity] for entity in common], dtype=float)
    bundle = joint_path_bundle(matrix, center, seed=seed)
    paths = np.asarray(bundle["nominal_paths"], dtype=float)
    terminal = np.prod(1.0 + paths, axis=1) - 1.0
    shared_hash = stable_id("joint-path-bundle", common, bundle)
    records = [
        _record(
            module="P5.S5.M05", model=model, underlying=underlying,
            target_id="joint_return_scenario_5d",
            distribution=_scenario_distribution(terminal[:, column], "joint"),
            as_of_time=as_of_time, cutoff=cutoff,
            resolver="qualified-copula-multistep", family="JOINT_SCENARIO",
            horizon="5D", metadata={
                "shared_path_bundle_hash": shared_hash,
                "joint_entities": common,
                "entity_column": column,
                "scenario_bundle": bundle,
                "generator_scope": "MULTIVARIATE_PATH",
            },
        )
        for column, underlying in enumerate(common)
    ]
    return HandlerOutcome(values=(_panel(records),))


def m06(payload: dict[str, Any]) -> HandlerOutcome:
    panels = [
        _panel_value(value)
        for name, value in payload.items()
        if name.startswith(("tail_member_", "scenario_member_")) and isinstance(value, dict)
    ]
    records = [record.model_dump(mode="json") for panel in panels for record in panel.records]
    distribution_report = validate_distribution_set(records)
    scenario_reports = []
    seen: set[str] = set()
    for panel in panels:
        for record in panel.records:
            bundle = record.metadata.get("scenario_bundle")
            if not isinstance(bundle, dict):
                continue
            bundle_id = stable_id("scenario-bundle", bundle)
            if bundle_id in seen:
                continue
            seen.add(bundle_id)
            scenario_reports.append({"bundle_id": bundle_id, **validate_scenario_bundle(bundle)})
    failures = list(distribution_report["failures"])
    failures.extend(
        {"bundle_id": row["bundle_id"], "reason": reason}
        for row in scenario_reports for reason in row["failures"]
    )
    if failures:
        raise DataQualityError(f"tail/scenario validation failed: {failures}")
    report = {
        **distribution_report,
        "passed": True,
        "scenario_bundle_reports": scenario_reports,
        "qualification_policy": "MASS_FINITE_DIVERSITY_ENERGY_VARIROGRAM_TAIL_STRESS_SEPARATION",
    }
    return HandlerOutcome(values=({"records": records, "validated": True}, report))


def _scenario_distribution(values: np.ndarray, prefix: str) -> ScenarioDistribution:
    array = np.asarray(values, dtype=float)
    probability = 1.0 / len(array)
    return ScenarioDistribution(scenarios=tuple(
        ScenarioPoint(scenario_id=f"{prefix}-{index:04d}", value=float(value), probability=probability)
        for index, value in enumerate(array)
    ))


def _cumulative_terminal(paths: np.ndarray) -> np.ndarray:
    if paths.ndim != 2 or np.any(paths <= -1.0):
        raise DataQualityError("univariate paths must be a valid return matrix")
    return np.prod(1.0 + paths, axis=1) - 1.0


def _record(
    *, module, model, underlying, target_id, distribution, as_of_time, cutoff,
    resolver, family, horizon="1D", unit="decimal_return", metadata=None,
):
    enriched = {
        **(metadata or {}),
        "source_return_resolver_id": model["resolver_id"],
        "source_return_model_artifact_id": model["model_artifact_id"],
        "conditioning": "CURRENT_RETURN_FORECAST_PLUS_OOF_RESIDUAL",
        "algorithm_version": "RC34-INTEGRATION-HARDENED-P4-V14.9-NATIVE",
        "evidence_cutoff": cutoff.isoformat(),
    }
    return ForecastMemberRecord(
        record_id=stable_id(module, model["resolver_id"], resolver, underlying, target_id, as_of_time),
        as_of_time=as_of_time,
        prediction_timestamp=horizon_end(as_of_time, horizon),
        underlying=underlying,
        target_id=target_id,
        horizon=horizon,
        unit=unit,
        resolver_id=resolver,
        resolver_family=family,
        model_artifact_id=stable_id("derived-tail-model", module, model["model_artifact_id"], cutoff, enriched),
        feature_view_id=model["feature_view_id"],
        training_cutoff=cutoff,
        lineage_id=stable_id("tail-lineage", module, model["model_artifact_id"], resolver, underlying, cutoff),
        distribution=distribution,
        role="CHALLENGER",
        metadata=enriched,
    )


def _mapping(payload: dict[str, Any], name: str) -> dict[str, Any]:
    value = payload.get(name)
    if not isinstance(value, dict):
        raise DataQualityError(f"{name} must be an object")
    return value


def _panel(records):
    if not records:
        raise DataQualityError("tail/scenario resolver produced no records")
    return ForecastMemberPanel(records=tuple(records))


def _panel_value(value: Any) -> ForecastMemberPanel:
    return value if isinstance(value, ForecastMemberPanel) else ForecastMemberPanel.model_validate(value)
