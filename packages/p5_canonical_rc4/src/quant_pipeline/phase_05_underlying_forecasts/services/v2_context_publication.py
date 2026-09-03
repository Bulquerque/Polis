"""Strong V2 dependence, regime/OOD and forecast-confidence publication."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np

from ..domain.v2_base import CalibrationStatus, ValidityStatus
from ..domain.v2_publication import ForecastConfidence, ForecastConfidenceRecord
from ..domain.v2_scenarios import DependenceState, DependenceStateRecord, RegimeOODState, RegimeOODStateRecord
from .identifiers import as_utc, stable_id
from .v2_artifacts import identity_fields


def build_dependence_artifact(registry: dict[str, Any] | None, *, run_id: str, cycle_id: str, decision_time: str, created_at: str) -> dict[str, Any]:
    rows = []
    for raw in (registry or {}).get("records", []):
        diagnostics = raw.get("diagnostics", {})
        if not raw.get("validated") or "matrix" not in raw or "correlation_matrix" not in raw:
            continue
        effective_rank = diagnostics.get("effective_rank")
        condition_number = diagnostics.get("condition_number")
        repair_magnitude = raw.get("repair_magnitude", diagnostics.get("repair_ratio"))
        psd_status = raw.get("psd_status")
        if any(value is None for value in (effective_rank, condition_number, repair_magnitude, psd_status)):
            continue
        rows.append(DependenceStateRecord(
            covariance_type=str(raw.get("covariance_type", raw.get("conditioning", "UNSPECIFIED_COVARIANCE"))),
            covariance_matrix=tuple(tuple(float(value) for value in line) for line in raw["matrix"]),
            correlation_matrix=tuple(tuple(float(value) for value in line) for line in raw["correlation_matrix"]),
            effective_rank=float(effective_rank),
            condition_number=max(1.0, float(condition_number)),
            psd_status=str(psd_status),
            repair_magnitude=max(0.0, float(repair_magnitude)),
            estimation_window=(as_utc(raw.get("evidence_cutoff", decision_time)), as_utc(raw.get("as_of_time", decision_time))),
            underlying_order=tuple(str(value) for value in raw["entities"]),
            horizon=str(raw.get("horizon", "1D")),
            champion_status=str(raw.get("champion_status", "CHALLENGER")),
            lineage_id=str(raw.get("lineage_id", stable_id("dependence-lineage", raw))),
        ))
    return _artifact_or_unavailable(DependenceState, rows, "P5.S9.M03", run_id, cycle_id, decision_time, created_at, "P5_COVARIANCE_UNSTABLE")


def build_regime_ood_artifact(
    regime: dict[str, Any] | None,
    change_point: dict[str, Any] | None,
    ood: dict[str, Any] | None,
    context: dict[str, Any] | None,
    *,
    run_id: str,
    cycle_id: str,
    decision_time: str,
    created_at: str,
) -> dict[str, Any]:
    regime_map = _regime_map(regime)
    ood_map = _ood_map(ood)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in (context or {}).get("records", []):
        grouped[(str(row.get("underlying")), str(row.get("horizon", "1D")))].append(row)
    records = []
    for key, rows in sorted(grouped.items()):
        base = regime_map.get(key) or regime_map.get(("MARKET_AGGREGATE", key[1])) or {}
        probabilities = dict(rows[0].get("regime_probabilities") or base.get("probabilities") or {})
        if not probabilities:
            continue
        probabilities = _normalize(probabilities)
        transition = _transition(base)
        ood_values = ood_map.get(key, {})
        change_values = [float(row["change_point_probability"]) for row in rows if row.get("change_point_probability") is not None]
        global_change = (change_point or {}).get("change_point_probability")
        if global_change is not None:
            change_values.append(float(global_change))
        change = max(change_values) if change_values else None
        severity_inputs = [value for value in (
            change,
            ood_values.get("feature_ood"),
            ood_values.get("market_state_ood"),
            ood_values.get("dependence_ood"),
            _maximum_optional(rows, "context_uncertainty"),
        ) if value is not None]
        reason_codes = []
        if change is None:
            reason_codes.append("P5_CHANGE_POINT_UNAVAILABLE")
        if not any(value is not None for value in ood_values.values()):
            reason_codes.append("P5_OOD_EVIDENCE_UNAVAILABLE")
        validity = ValidityStatus.VALID if not reason_codes else ValidityStatus.DEGRADED
        records.append(RegimeOODStateRecord(
            underlying=key[0], horizon=key[1], regime_probabilities=probabilities,
            transition_probabilities=transition,
            expected_duration={str(name): float(value) for name, value in base.get("expected_duration", {}).items()},
            change_point_probability=None if change is None else float(np.clip(change, 0.0, 1.0)),
            feature_ood=_optional_nonnegative(ood_values.get("feature_ood")),
            model_ood=_optional_nonnegative(ood_values.get("model_ood")),
            market_state_ood=_optional_nonnegative(ood_values.get("market_state_ood")),
            dependence_ood=_optional_nonnegative(ood_values.get("dependence_ood")),
            severity=_severity(max(severity_inputs)) if severity_inputs else "UNAVAILABLE",
            validity_status=validity,
            reason_codes=tuple(reason_codes),
            lineage_id=stable_id("regime-ood-v2", key, base.get("lineage_id"), [row.get("record_id") for row in rows], ood_values),
        ))
    return _artifact_or_unavailable(RegimeOODState, records, "P5.S9.M03", run_id, cycle_id, decision_time, created_at, "P5_REGIME_UNSTABLE")


def build_confidence_artifact(panel: dict[str, Any] | None, *, run_id: str, cycle_id: str, decision_time: str, created_at: str) -> dict[str, Any]:
    records = []
    for row in (panel or {}).get("records", []):
        records.append(ForecastConfidenceRecord(
            underlying=str(row["underlying"]), target_id=str(row["target_id"]), horizon=str(row["horizon"]),
            calibration_component=_optional_component(row, "calibration_component"),
            data_quality_component=_optional_component(row, "data_quality_component"),
            model_stability_component=_optional_component(row, "model_stability_component"),
            ensemble_disagreement_component=_optional_component(row, "ensemble_disagreement_component"),
            ood_component=_optional_component(row, "ood_component"),
            regime_uncertainty_component=_optional_component(row, "regime_uncertainty_component"),
            overall_confidence=float(_required(row, "overall_confidence", "confidence")),
            confidence_method=str(row.get("confidence_method", "UNAVAILABLE")),
            calibration_version=str(row.get("calibration_version", "UNAVAILABLE")),
            calibration_status=CalibrationStatus(str(row.get("calibration_status", "UNCALIBRATED"))),
            abstained=bool(row.get("abstained", False)), lineage_id=str(row["lineage_id"]),
        ))
    return _artifact_or_unavailable(ForecastConfidence, records, "P5.S9.M03", run_id, cycle_id, decision_time, created_at, "P5_CONFIDENCE_UNCALIBRATED")


def _artifact_or_unavailable(model, records, module_id, run_id, cycle_id, decision_time, created_at, reason_code):
    if not records:
        content = {"artifact_type": model.__name__, "availability": "UNAVAILABLE", "reason_code": reason_code}
        identity = identity_fields(
            module_id=module_id, run_id=run_id, cycle_id=cycle_id,
            decision_time=decision_time, created_at=created_at,
            payload=content, lineage_inputs=(model.__name__, "UNAVAILABLE"),
        )
        return {**content, **{key: value.isoformat() if hasattr(value, "isoformat") else value for key, value in identity.items()}}
    content = {"records": [row.model_dump(mode="json") for row in records]}
    identity = identity_fields(
        module_id=module_id, run_id=run_id, cycle_id=cycle_id,
        decision_time=decision_time, created_at=created_at,
        payload=content, lineage_inputs=[row.lineage_id for row in records],
    )
    return {"availability": "AVAILABLE", "artifact": model(**identity, records=tuple(records)).model_dump(mode="json")}


def _regime_map(regime):
    output = {}
    for row in (regime or {}).get("records", []):
        output[(str(row.get("underlying")), str(row.get("horizon", "1D")))] = row
    if regime and not output and regime.get("probabilities"):
        output[("MARKET_AGGREGATE", str(regime.get("horizon", "1D")))] = regime
    return output


def _ood_map(ood):
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in (ood or {}).get("records", []):
        grouped[(str(row.get("underlying")), str(row.get("horizon", "1D")))].append(row)
    fields = ("feature_ood", "model_ood", "market_state_ood", "dependence_ood")
    return {key: {name: _maximum_optional(rows, name) for name in fields} for key, rows in grouped.items()}


def _maximum_optional(rows, name):
    values = [float(row[name]) for row in rows if row.get(name) is not None]
    return max(values) if values else None


def _transition(row):
    labels = [str(value) for value in row.get("regime_labels", [])]
    matrix = row.get("transition_matrix", [])
    if len(labels) != len(matrix):
        return {}
    return {labels[i]: {labels[j]: float(matrix[i][j]) for j in range(len(labels))} for i in range(len(labels))}


def _normalize(values):
    total = sum(max(float(value), 0.0) for value in values.values())
    if total <= 0.0:
        raise ValueError("regime probability mass must be positive")
    return {str(name): max(float(value), 0.0) / total for name, value in values.items()}


def _optional_nonnegative(value):
    return None if value is None else max(0.0, float(value))


def _severity(value):
    if value >= 0.90:
        return "SEVERE"
    if value >= 0.65:
        return "HIGH"
    if value >= 0.35:
        return "MODERATE"
    return "LOW"


def _required(row: dict[str, Any], primary: str, fallback: str) -> Any:
    value = row.get(primary, row.get(fallback))
    if value is None:
        raise ValueError(f"missing required confidence field: {primary}")
    return value


def _optional_component(row: dict[str, Any], name: str) -> float | None:
    value = row.get(name)
    return None if value is None else float(value)
