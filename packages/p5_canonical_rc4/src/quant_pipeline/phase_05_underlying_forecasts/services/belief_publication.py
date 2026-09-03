"""Fail-closed ambiguity and P6-native market-belief publication."""
from __future__ import annotations

import re
from typing import Any

import numpy as np

from ..domain.forecast import EnsembleForecastPanel
from ..errors import DataQualityError
from .identifiers import stable_id

_HORIZON = re.compile(r"^(?P<count>[1-9]\d*)(?P<unit>[HDWM])$")

def build_ambiguity_set(
    scenarios: dict[str, Any],
    confidence_panel: dict[str, Any] | None = None,
    context_panel: dict[str, Any] | None = None,
) -> dict[str, Any]:
    confidence = {
        str(row["record_id"]): float(row["confidence"])
        for row in (confidence_panel or {}).get("records", [])
        if row.get("record_id") is not None and row.get("confidence") is not None
    }
    context = {
        _context_key(row): float(row["context_uncertainty"])
        for row in (context_panel or {}).get("records", [])
        if row.get("context_uncertainty") is not None
    }
    records = []
    for raw in scenarios.get("records", []):
        values, probabilities = scenario_values_and_probabilities(raw)
        if len(values) < 2:
            continue
        record_id = str(raw.get("record_id"))
        conf = confidence.get(record_id)
        uncertainty = context.get(_context_key(raw))
        if conf is None or uncertainty is None:
            continue
        alternatives = _probability_stresses(values, probabilities, uncertainty, conf)
        records.append({
            "ambiguity_set_id": stable_id("ambiguity-set", raw.get("record_id"), alternatives),
            "source_record_id": raw.get("record_id"),
            "underlying": raw.get("underlying"),
            "target_id": raw.get("target_id"),
            "horizon": raw.get("horizon"),
            "unit": raw.get("unit"),
            "scenario_count": len(values),
            "base_probabilities": probabilities,
            "alternative_probabilities": alternatives,
            "construction_method": "EMPIRICAL_PLUS_TAIL_AND_CONCENTRATION_STRESS",
            "stress_is_not_assigned_empirical_likelihood": True,
            "confidence": conf,
            "context_uncertainty": uncertainty,
        })
    return {
        "availability": "AVAILABLE" if records else "UNAVAILABLE",
        "records": records,
        "capability": "EMPIRICAL_AND_STRESS_BASELINE" if records else "UNAVAILABLE",
    }


def build_market_belief_state(
    panel: EnsembleForecastPanel,
    scenarios: dict[str, Any],
    ambiguity: dict[str, Any],
    context: dict[str, Any] | None,
    *,
    decision_time: str,
    confidence_panel: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scenario_map = {str(row.get("record_id")): row for row in scenarios.get("records", [])}
    ambiguity_map = {str(row.get("source_record_id")): row for row in ambiguity.get("records", [])}
    context_map = {_context_key(row): row for row in (context or {}).get("records", [])}
    confidence_map = {
        _context_key(row): row
        for row in (confidence_panel or {}).get("records", [])
    }
    records = []
    diagnostics = []
    for row in panel.records:
        key = _record_key(row)
        record, diagnostic = _belief_record(
            row,
            scenario_map.get(row.record_id),
            ambiguity_map.get(row.record_id),
            context_map.get(key),
            confidence_map.get(key),
            decision_time,
        )
        records.append(record)
        diagnostics.append(diagnostic)
    return {
        "records": records,
        "record_count": len(records),
        "schema_version": "P5-P6-MARKET-BELIEF-V2",
        "capability_diagnostics": diagnostics,
    }


def _belief_record(
    row: Any,
    scenario: dict[str, Any] | None,
    ambiguity: dict[str, Any] | None,
    context: dict[str, Any] | None,
    confidence_evidence: dict[str, Any] | None,
    decision_time: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    values, probabilities = scenario_values_and_probabilities(scenario or {})
    anchor = _price_anchor(row, scenario)
    semantics = scenario_semantics(row.unit)
    confidence_status = str((confidence_evidence or {}).get("calibration_status", "UNAVAILABLE"))
    calibrated = confidence_status in {"CALIBRATED", "PARTIALLY_CALIBRATED"}
    abstained = bool((confidence_evidence or {}).get("abstained", row.abstained))
    belief_scenarios: list[dict[str, Any]] = []
    if calibrated and not abstained and anchor is not None and values and semantics in {"RETURN", "PRICE"}:
        prices = values if semantics == "PRICE" else [anchor * (1.0 + value) for value in values]
        if all(np.isfinite(prices)) and all(value >= 0.0 for value in prices):
            belief_scenarios = [{
                "scenario_id": stable_id("belief-scenario", row.record_id, index),
                "terminal_underlying_price": float(price),
                "probability": float(probabilities[index]),
                "path_prices": [],
            } for index, price in enumerate(prices)]
    record = {
        "belief_state_id": stable_id("market-belief", row.record_id),
        "underlying_id": row.underlying,
        "decision_time": decision_time,
        "horizon_days": _horizon_days(row.horizon),
        "scenarios": belief_scenarios,
        "confidence": float((confidence_evidence or {}).get("overall_confidence", row.confidence)),
        "regime_context": _regime_context(context),
        "ambiguity_set_id": ambiguity.get("ambiguity_set_id") if ambiguity else None,
        "ambiguity_probabilities": ambiguity.get("alternative_probabilities", []) if belief_scenarios and ambiguity else [],
        "scenario_capability": "AVAILABLE" if belief_scenarios else "LIMITED",
        "ambiguity_capability": "AVAILABLE" if belief_scenarios and ambiguity else "UNAVAILABLE",
        "surface_capability": "UNAVAILABLE",
        "source_artifact_id": row.record_id,
    }
    diagnostic = {
        "belief_state_id": record["belief_state_id"],
        "underlying_id": row.underlying,
        "calibration_status": confidence_status,
        "abstained": abstained,
        "capability_reason_codes": _belief_reason_codes(
            calibrated=calibrated,
            abstained=abstained,
            anchor=anchor,
            values=values,
            semantics=semantics,
            ambiguity=ambiguity,
        ),
    }
    return record, diagnostic



def scenario_values_and_probabilities(raw: dict[str, Any]) -> tuple[list[float], list[float]]:
    if raw.get("scenarios"):
        values = []
        probabilities = []
        for item in raw["scenarios"]:
            value = item.get("value", item.get("terminal_value"))
            probability = item.get("probability")
            if value is None or probability is None:
                raise DataQualityError("explicit scenarios require value and probability")
            values.append(float(value))
            probabilities.append(float(probability))
    else:
        samples = raw.get("samples") or (raw.get("distribution", {}) or {}).get("samples", [])
        values = [float(value) for value in samples]
        probabilities = [1.0 / len(values)] * len(values) if values else []
    if not values:
        return [], []
    if not all(np.isfinite(values)) or not all(np.isfinite(probabilities)):
        raise DataQualityError("scenario values and probabilities must be finite")
    if any(value < 0.0 for value in probabilities):
        raise DataQualityError("scenario probabilities must be nonnegative")
    total = float(sum(probabilities))
    if total <= 0.0:
        raise DataQualityError("scenario probability mass must be positive")
    if raw.get("scenarios") and abs(total - 1.0) > 1e-8:
        raise DataQualityError("explicit scenario probability mass must equal one")
    return values, [value / total for value in probabilities]


def _regime_context(context: dict[str, Any] | None) -> str:
    if not context:
        return "UNAVAILABLE"
    value = context.get("dominant_regime", context.get("regime_label"))
    return "UNAVAILABLE" if value is None else str(value)


def _belief_reason_codes(*, calibrated, abstained, anchor, values, semantics, ambiguity):
    reasons = []
    if not calibrated:
        reasons.append("P5_CONFIDENCE_UNCALIBRATED")
    if abstained:
        reasons.append("P5_SEVERE_OOD")
    if anchor is None:
        reasons.append("P5_PRICE_ANCHOR_UNAVAILABLE")
    if not values:
        reasons.append("P5_SCENARIO_MASS_INVALID")
    if semantics not in {"RETURN", "PRICE"}:
        reasons.append("P5_TARGET_UNAVAILABLE")
    if ambiguity is None:
        reasons.append("P5_AMBIGUITY_UNAVAILABLE")
    return reasons


def _probability_stresses(values, base, uncertainty, confidence):
    array = np.asarray(values, dtype=float)
    weights = np.asarray(base, dtype=float)
    severity = float(np.clip(0.10 + 0.35 * uncertainty + 0.20 * (1.0 - confidence), 0.10, 0.60))
    lower_count = max(1, len(array) // 5)
    alternatives = [weights]
    for indexes in (np.argsort(array)[:lower_count], np.argsort(array)[::-1][:lower_count]):
        vector = weights.copy(); vector[indexes] += severity / lower_count; alternatives.append(vector / np.sum(vector))
    concentrated = weights.copy(); concentrated[int(np.argmax(weights))] += severity; alternatives.append(concentrated / np.sum(concentrated))
    return [[float(value) for value in vector] for vector in alternatives]


def _price_anchor(row: Any, scenario: dict[str, Any] | None = None) -> float | None:
    sources = [scenario or {}, getattr(row, "metadata", {}) or {}]
    for source in sources:
        for key in ("spot_price", "underlying_price", "price_anchor"):
            if source.get(key) is not None:
                value = float(source[key])
                if np.isfinite(value) and value > 0.0:
                    return value
    return None


def scenario_semantics(unit: str) -> str:
    normalized = unit.lower()
    if "price" in normalized: return "PRICE"
    if "return" in normalized: return "RETURN"
    if "vol" in normalized or "variance" in normalized: return "VOLATILITY"
    return "UNKNOWN"


def _horizon_days(horizon: str) -> int:
    """Convert the wire horizon to calendar days using the P5→P6 contract.

    Hour horizons are accepted only when they represent a whole number of days.
    This intentionally fails closed for sub-day beliefs because P6 candidate
    expirations are currently day-granular.
    """
    match = _HORIZON.fullmatch(horizon.strip().upper())
    if match is None:
        raise DataQualityError(f"invalid horizon: {horizon}")
    count = int(match.group("count"))
    unit = match.group("unit")
    if unit == "H":
        if count % 24:
            raise DataQualityError(
                f"sub-day horizon {horizon!r} is not supported by the P5→P6 day-granular contract"
            )
        return count // 24
    if unit == "D":
        return count
    if unit == "W":
        return 7 * count
    return 30 * count


def _record_key(row: Any) -> tuple[str, str, str, str]:
    return row.underlying, row.target_id, row.horizon, row.unit


def _context_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return tuple(str(row.get(name, "")) for name in ("underlying", "target_id", "horizon", "unit"))  # type: ignore[return-value]


