"""Strong V2 scenario paths and empirically calibrated ambiguity sets."""
from __future__ import annotations

from typing import Any

import numpy as np

from ..domain.v2_base import ScenarioType, ValidityStatus
from ..domain.v2_scenarios import AmbiguitySet, AmbiguitySetRecord, ScenarioPathPanel, ScenarioPathRecord
from ..errors import DataQualityError
from .calendar import default_calendar
from .identifiers import as_utc, stable_hash, stable_id
from .v2_artifacts import identity_fields


def build_scenario_artifacts(
    validated_registry: dict[str, Any],
    *,
    run_id: str,
    cycle_id: str,
    decision_time: str,
    created_at: str,
    confidence_panel: dict[str, Any] | None = None,
    context_panel: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    records: list[ScenarioPathRecord] = []
    ambiguity_records: list[AmbiguitySetRecord] = []
    confidence = _confidence_map(confidence_panel)
    context = _context_map(context_panel)
    selected: dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any]]] = {}
    for raw in validated_registry.get("records", []):
        bundle = raw.get("metadata", {}).get("scenario_bundle")
        if not isinstance(bundle, dict):
            continue
        key = (str(raw.get("underlying")), str(raw.get("horizon")))
        current = selected.get(key)
        if current is None or _scenario_rank(raw, bundle) < _scenario_rank(*current):
            selected[key] = (raw, bundle)
    for raw, bundle in selected.values():
        records.extend(_scenario_records(raw, bundle, decision_time))
        ambiguity_records.append(_ambiguity_record(raw, bundle, confidence, context))
    if len(records) < 2:
        return _unavailable("ScenarioPathPanel", "P5.S9.M02", run_id, cycle_id, decision_time, created_at), _unavailable(
            "AmbiguitySet", "P5.S9.M02", run_id, cycle_id, decision_time, created_at,
        )
    scenario_content = {"records": [row.model_dump(mode="json") for row in records]}
    scenario_identity = identity_fields(
        module_id="P5.S9.M02", run_id=run_id, cycle_id=cycle_id,
        decision_time=decision_time, created_at=created_at,
        payload=scenario_content, lineage_inputs=[row.lineage_id for row in records],
    )
    scenario_panel = ScenarioPathPanel(**scenario_identity, records=tuple(records))
    ambiguity_content = {"records": [row.model_dump(mode="json") for row in ambiguity_records]}
    ambiguity_identity = identity_fields(
        module_id="P5.S9.M02", run_id=run_id, cycle_id=cycle_id,
        decision_time=decision_time, created_at=created_at,
        payload=ambiguity_content, lineage_inputs=[row.lineage_id for row in ambiguity_records],
    )
    ambiguity = AmbiguitySet(**ambiguity_identity, records=tuple(ambiguity_records))
    return (
        {"availability": "AVAILABLE", "artifact": scenario_panel.model_dump(mode="json")},
        {"availability": "AVAILABLE", "artifact": ambiguity.model_dump(mode="json"), "capability": "EMPIRICAL_AND_STRESS"},
    )


def _scenario_rank(raw: dict[str, Any], bundle: dict[str, Any]) -> tuple[int, float, str]:
    joint = raw.get("metadata", {}).get("generator_scope") == "MULTIVARIATE_PATH"
    scores = [float(row.get("qualification_score", float("inf"))) for row in bundle.get("candidate_scores", [])]
    return (0 if joint else 1, min(scores, default=float("inf")), str(raw.get("record_id", "")))


def _scenario_records(raw: dict[str, Any], bundle: dict[str, Any], decision_time: str) -> list[ScenarioPathRecord]:
    paths = np.asarray(bundle.get("nominal_paths", ()), dtype=float)
    probabilities = np.asarray(bundle.get("nominal_probabilities", ()), dtype=float)
    if paths.ndim not in {2, 3} or probabilities.shape != (len(paths),):
        raise DataQualityError("validated scenario bundle has incompatible path/probability shape")
    if abs(float(np.sum(probabilities)) - 1.0) > 1e-8:
        raise DataQualityError("validated scenario bundle probability mass is invalid")
    output: list[ScenarioPathRecord] = []
    for scenario_index, path in enumerate(paths):
        output.extend(_path_records(raw, path, scenario_index, float(probabilities[scenario_index]), bundle, ScenarioType.NOMINAL, decision_time=decision_time))
    for stress_index, stress in enumerate(bundle.get("stress_paths", [])):
        if stress.get("probability") is not None:
            raise DataQualityError("deterministic stress scenario cannot claim probability")
        output.extend(_path_records(raw, np.asarray(stress["path"], dtype=float), stress_index, None, bundle, ScenarioType.STRESS, stress, decision_time))
    return output


def _path_records(raw, path, index, probability, bundle, scenario_type, stress=None, decision_time=None):
    vector = _entity_path(raw, np.asarray(path, dtype=float))
    calendar = default_calendar()
    decision = as_utc(decision_time)
    scenario_id = str(stress.get("stress_id")) if stress else stable_id("scenario", raw["record_id"], index, bundle["champion_method"])
    flags = (str(stress.get("stress_type")),) if stress else ()
    output = []
    cumulative = 1.0
    for step, value in enumerate(vector, start=1):
        cumulative *= 1.0 + float(value)
        output.append(ScenarioPathRecord(
            underlying=str(raw["underlying"]), decision_time=decision, horizon=str(raw["horizon"]),
            scenario_id=scenario_id, scenario_type=scenario_type, probability=probability,
            path_step=step, path_timestamp=calendar.advance_sessions(decision, step),
            future_return=float(cumulative - 1.0),
            realized_volatility_state=float(np.sqrt(np.sum(np.square(vector[:step])))),
            implied_volatility_state=None, skew_state=None, term_structure_state=None,
            liquidity_state=None, regime_state=None,
            jump_state=bool(abs(float(value)) > 3.0 * max(float(np.std(vector)), 1e-8)),
            stress_flags=flags, seed=int(bundle.get("seed", 0)),
            generator_id=str(bundle.get("champion_method", "UNAVAILABLE")),
            lineage_id=stable_id("scenario-path-lineage", raw.get("lineage_id"), scenario_id, step),
        ))
    return output


def _entity_path(raw: dict[str, Any], path: np.ndarray) -> np.ndarray:
    if path.ndim == 1:
        return path
    column = int(raw.get("metadata", {}).get("entity_column", 0))
    if path.ndim != 2 or not 0 <= column < path.shape[1]:
        raise DataQualityError("joint scenario entity column is invalid")
    return path[:, column]


def _ambiguity_record(raw, bundle, confidence, context):
    scores = bundle.get("candidate_scores", [])
    ids = tuple(stable_id("plausible-distribution", raw["record_id"], row.get("method"), row) for row in scores)
    if not ids:
        ids = (stable_id("plausible-distribution", raw["record_id"], bundle.get("champion_method")),)
    stress_ids = tuple(str(row.get("stress_id")) for row in bundle.get("stress_paths", []) if row.get("stress_id"))
    values = np.asarray([float(row["qualification_score"]) for row in scores if row.get("qualification_score") is not None], dtype=float)
    empirical_spread = float(np.std(values)) if len(values) > 1 else 0.0
    key = (str(raw.get("underlying")), str(raw.get("target_id")), str(raw.get("horizon")))
    conf = confidence.get(key)
    contextual = context.get(key)
    evidence_complete = conf is not None and contextual is not None
    radius = empirical_spread
    if conf is not None:
        radius += 0.05 * (1.0 - conf)
    if contextual is not None:
        radius += 0.05 * contextual
    radius = max(1e-8, radius)
    return AmbiguitySetRecord(
        nominal_distribution_id=stable_id("nominal-distribution", raw["record_id"], bundle.get("champion_method")),
        ambiguity_method="EMPIRICAL_MODEL_BOOTSTRAP_REGIME_CALIBRATION_PLUS_STRESS",
        radius_or_band=radius,
        calibration_sample_size=int(bundle.get("effective_scenario_count", len(bundle.get("nominal_paths", [])))),
        coverage_target=0.90,
        plausible_distribution_ids=ids,
        stress_distribution_ids=stress_ids,
        scope={"underlying": key[0], "target_id": key[1], "horizon": key[2]},
        validity_status=ValidityStatus.VALID if evidence_complete else ValidityStatus.DEGRADED,
        lineage_id=stable_id("ambiguity-lineage", raw.get("lineage_id"), ids, stress_ids, radius),
    )


def _confidence_map(panel):
    return {
        (str(row.get("underlying")), str(row.get("target_id")), str(row.get("horizon"))): float(row.get("overall_confidence", row.get("confidence")))
        for row in (panel or {}).get("records", [])
        if row.get("overall_confidence", row.get("confidence")) is not None
    }


def _context_map(panel):
    grouped: dict[tuple[str, str, str], list[float]] = {}
    for row in (panel or {}).get("records", []):
        key = (str(row.get("underlying")), str(row.get("target_id")), str(row.get("horizon")))
        if row.get("context_uncertainty") is not None:
            grouped.setdefault(key, []).append(float(row["context_uncertainty"]))
    return {key: float(np.mean(values)) for key, values in grouped.items()}


def _unavailable(name, module_id, run_id, cycle_id, decision_time, created_at):
    content = {"artifact_type": name, "availability": "UNAVAILABLE", "reason_code": "P5_SCENARIO_MASS_INVALID"}
    identity = identity_fields(
        module_id=module_id, run_id=run_id, cycle_id=cycle_id,
        decision_time=decision_time, created_at=created_at,
        payload=content, lineage_inputs=(name, "UNAVAILABLE"),
    )
    return {**content, **{key: value.isoformat() if hasattr(value, "isoformat") else value for key, value in identity.items()}}
