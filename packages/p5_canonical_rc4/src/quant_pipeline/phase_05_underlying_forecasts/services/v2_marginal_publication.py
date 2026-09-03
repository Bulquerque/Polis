"""Strong, fail-closed V2 publication for marginal and path-risk forecasts."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np

from ..domain.distributions import QuantilePoint, point_value
from ..domain.forecast import EnsembleForecastPanel
from ..domain.v2_base import CalibrationStatus, CapabilityStatus, ValidityStatus
from ..domain.v2_marginals import (
    PathRiskForecastPanel,
    PathRiskForecastRecord,
    ReturnDistributionPanel,
    ReturnDistributionRecord,
    VolatilityDistributionPanel,
    VolatilityDistributionRecord,
)
from .identifiers import stable_id
from .v2_artifacts import distribution_statistics, identity_fields


def build_marginal_artifacts(
    panel: EnsembleForecastPanel,
    *,
    run_id: str,
    cycle_id: str,
    decision_time: str,
    created_at: str,
    confidence_panel: dict[str, Any] | None = None,
) -> dict[str, Any]:
    calibration = _calibration_map(confidence_panel)
    return_records = [_return_record(row, decision_time, calibration) for row in panel.records if _is_return(row)]
    volatility_records = _volatility_records(panel, decision_time, calibration)
    path_records = _path_records(panel, decision_time)
    return {
        "return_distributions": _artifact_or_unavailable(
            ReturnDistributionPanel, return_records, "P5.S9.M02", decision_time, run_id, cycle_id, created_at,
        ),
        "volatility_distributions": _artifact_or_unavailable(
            VolatilityDistributionPanel, volatility_records, "P5.S9.M02", decision_time, run_id, cycle_id, created_at,
        ),
        "path_risk_forecasts": _artifact_or_unavailable(
            PathRiskForecastPanel, path_records, "P5.S9.M02", decision_time, run_id, cycle_id, created_at,
        ),
    }


def _return_record(row: Any, decision_time: str, calibration: dict[str, dict[str, Any]]) -> ReturnDistributionRecord:
    stats = distribution_statistics(row.distribution)
    return ReturnDistributionRecord(
        underlying=row.underlying,
        decision_time=decision_time,
        horizon=row.horizon,
        target_id=row.target_id,
        distribution_version="RC34-MARGINAL-V2",
        mean=stats["mean"],
        median=stats["median"],
        mode=stats["mode"],
        mode_method=stats["mode_method"],
        quantiles=tuple(QuantilePoint(level=level, value=value) for level, value in stats["quantiles"]),
        probability_positive=stats["probability_positive"],
        probability_negative=stats["probability_negative"],
        tail_probabilities=stats["tail_probabilities"],
        tail_probability_semantics=stats["tail_probability_semantics"],
        distribution_family=stats["distribution_family"],
        support=stats["support"],
        units=row.unit,
        model_member_ids=row.member_ids,
        calibration_status=_calibration_status(row, calibration),
        confidence=row.confidence,
        distribution=row.distribution,
        lineage_id=row.lineage_id,
    )


def _volatility_records(panel: EnsembleForecastPanel, decision_time: str, calibration: dict[str, dict[str, Any]]) -> list[VolatilityDistributionRecord]:
    grouped: dict[tuple[str, str], dict[str, Any]] = defaultdict(dict)
    for row in panel.records:
        target = row.target_id.lower()
        if "volatility" not in target and "variance" not in target:
            continue
        key = (row.underlying, row.horizon)
        slot = "conditional" if "conditional" in target else "implied" if "implied" in target else "realized"
        grouped[key][slot] = row
    records = []
    for _, parts in sorted(grouped.items()):
        realized = parts.get("realized")
        conditional = parts.get("conditional")
        if realized is None and conditional is None:
            continue
        anchor = realized or conditional
        available = [row for row in (realized, conditional) if row is not None]
        status = CapabilityStatus.AVAILABLE if len(available) == 2 else CapabilityStatus.DEGRADED
        records.append(VolatilityDistributionRecord(
            underlying=anchor.underlying,
            decision_time=decision_time,
            forecast_horizon=anchor.horizon,
            realized_volatility_distribution=realized.distribution if realized else None,
            conditional_volatility_distribution=conditional.distribution if conditional else None,
            implied_volatility_state=parts.get("implied").distribution if parts.get("implied") else None,
            volatility_of_volatility=None,
            jump_variation=None,
            continuous_variation=realized.distribution if realized else None,
            units=anchor.unit,
            capability_status=status,
            model_member_ids=tuple(dict.fromkeys(
                member_id for row in available for member_id in row.member_ids
            )),
            calibration_status=_group_calibration_status(available, calibration),
            lineage_id=stable_id("volatility-v2", [row.lineage_id for row in available]),
        ))
    return records


def _path_records(panel: EnsembleForecastPanel, decision_time: str) -> list[PathRiskForecastRecord]:
    grouped: dict[tuple[str, str], dict[str, Any]] = defaultdict(dict)
    for row in panel.records:
        key = (row.underlying, row.horizon)
        target = row.target_id.lower()
        for label, patterns in {
            "minimum": ("path_minimum", "path_min"),
            "maximum": ("path_maximum", "path_max"),
            "drawdown": ("drawdown",),
            "jump": ("jump_probability", "jump"),
            "intraperiod": ("downside_volatility", "intraperiod_volatility"),
        }.items():
            if any(pattern in target for pattern in patterns):
                grouped[key][label] = row
    records = []
    for _, parts in sorted(grouped.items()):
        required = ("minimum", "maximum", "drawdown", "intraperiod")
        if any(name not in parts for name in required):
            continue
        anchor = parts["drawdown"]
        jump = float(np.clip(point_value(parts["jump"].distribution), 0.0, 1.0)) if "jump" in parts else None
        validity = ValidityStatus.VALID if "jump" in parts else ValidityStatus.DEGRADED
        records.append(PathRiskForecastRecord(
            underlying=anchor.underlying,
            decision_time=decision_time,
            horizon=anchor.horizon,
            path_minimum_distribution=parts["minimum"].distribution,
            path_maximum_distribution=parts["maximum"].distribution,
            maximum_drawdown_distribution=parts["drawdown"].distribution,
            jump_probability=jump,
            gap_probability=None,
            liquidity_stress_probability=None,
            intraperiod_volatility_distribution=parts["intraperiod"].distribution,
            liquidity_capability=CapabilityStatus.UNAVAILABLE,
            validity_status=validity,
            lineage_id=stable_id("path-risk-v2", *[parts[name].lineage_id for name in sorted(parts)]),
        ))
    return records


def _artifact_or_unavailable(model, records, module_id, decision_time, run_id, cycle_id, created_at):
    if not records:
        return _unavailable(model.__name__, module_id, decision_time, run_id, cycle_id, created_at)
    content = {"records": [row.model_dump(mode="json") for row in records]}
    identity = identity_fields(
        module_id=module_id, run_id=run_id, cycle_id=cycle_id,
        decision_time=decision_time, created_at=created_at,
        payload=content, lineage_inputs=[row.lineage_id for row in records],
    )
    return {"availability": "AVAILABLE", "artifact": model(**identity, records=tuple(records)).model_dump(mode="json")}


def _unavailable(name, module_id, decision_time, run_id, cycle_id, created_at):
    content = {"artifact_type": name, "availability": "UNAVAILABLE", "reason_code": "P5_TARGET_UNAVAILABLE"}
    identity = identity_fields(
        module_id=module_id, run_id=run_id, cycle_id=cycle_id,
        decision_time=decision_time, created_at=created_at,
        payload=content, lineage_inputs=(name, "UNAVAILABLE"),
    )
    return {**content, **{key: value.isoformat() if hasattr(value, "isoformat") else value for key, value in identity.items()}}


def _is_return(row: Any) -> bool:
    target = row.target_id.lower()
    return "return" in target and "path" not in target or "return" in row.unit.lower()


def _calibration_map(panel: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {str(row.get("record_id")): row for row in (panel or {}).get("records", []) if row.get("record_id")}


def _calibration_status(row: Any, calibration: dict[str, dict[str, Any]]) -> CalibrationStatus:
    evidence = calibration.get(str(row.record_id))
    if evidence is None:
        return CalibrationStatus.UNCALIBRATED
    status = str(evidence.get("calibration_status", "UNCALIBRATED"))
    return CalibrationStatus(status)


def _group_calibration_status(rows: Any, calibration: dict[str, dict[str, Any]]) -> CalibrationStatus:
    statuses = {_calibration_status(row, calibration) for row in rows if row is not None}
    if statuses == {CalibrationStatus.CALIBRATED}:
        return CalibrationStatus.CALIBRATED
    if CalibrationStatus.CALIBRATED in statuses or CalibrationStatus.PARTIALLY_CALIBRATED in statuses:
        return CalibrationStatus.PARTIALLY_CALIBRATED
    return CalibrationStatus.UNCALIBRATED
