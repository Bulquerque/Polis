"""Evidence-aware pruning, probabilistic mixtures and non-negative stacking."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np

from ..domain.distributions import (
    EmpiricalDistribution,
    MixtureComponent,
    MixtureDistribution,
    ParametricDistribution,
    PointDistribution,
    quantile_value,
)
from ..domain.forecast import (
    EnsembleForecastPanel,
    EnsembleForecastRecord,
    ForecastMemberPanel,
    ForecastMemberRecord,
    OOFValidationObservationPanel,
)
from ..errors import DataQualityError
from .ensemble_evidence import (
    aligned_matrix,
    compare_weighting_schemes,
    marginal_contributions,
    model_confidence_set,
    pairwise_evidence,
    stacking_weights,
    validation_profiles,
)
from .ensemble_scoring import calibrate, harmonize, score
from .ensemble_confidence import confidence_components, confidence_record
from .identifiers import stable_id

_MIN_OOF = 12
_EPS = 1e-12


def prune(
    panel: ForecastMemberPanel,
    scoring: dict[str, Any],
    max_candidates: int = 5,
    observations: OOFValidationObservationPanel | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    score_map = _score_map(scoring)
    profiles = validation_profiles(observations)
    grouped: dict[tuple[Any, ...], list[ForecastMemberRecord]] = defaultdict(list)
    for record in panel.records:
        if record.status == "VALID" and _resolver_key(record) in score_map:
            grouped[_group_key(record)].append(record)
    diversity_records, selected_ids = [], []
    for key, records in sorted(grouped.items()):
        selected, diagnostics = _select_group(key, records, score_map, profiles, max_candidates)
        if not selected:
            continue
        selected_ids.extend(record.record_id for record in selected)
        values = np.asarray([record.point_forecast for record in selected], dtype=float)
        diversity_records.append({
            "group": _serialized_group(key),
            "candidate_ids": [record.record_id for record in selected],
            "resolver_ids": [record.resolver_id for record in selected],
            "family_count": len({record.resolver_family for record in selected}),
            "target_diversity": len({record.target_id for record in selected}),
            "regime_diversity": len({str(record.metadata.get("regime", "UNAVAILABLE")) for record in selected}),
            "effective_candidate_count": _effective_count(np.ones(len(selected)) / len(selected)),
            "forecast_dispersion": float(np.std(values, ddof=0)),
            "selection_policy": "MCS_RESIDUAL_CORRELATION_COFAILURE_MARGINAL_CONTRIBUTION",
            **diagnostics,
        })
    if not selected_ids:
        raise DataQualityError("no calibrated resolver with sufficient OOF evidence is eligible")
    return {"records": diversity_records}, {"selected_record_ids": selected_ids}


def build_ensemble(
    panel: ForecastMemberPanel,
    candidates: dict[str, Any],
    scoring: dict[str, Any],
    context_router: dict[str, Any] | None,
    observations: OOFValidationObservationPanel | None = None,
    *,
    max_members: int = 3,
    confidence_floor: float = 0.20,
) -> tuple[EnsembleForecastPanel, dict[str, Any], dict[str, Any]]:
    selected = set(candidates.get("selected_record_ids", []))
    score_rows = _score_map(scoring)
    grouped: dict[tuple[Any, ...], list[ForecastMemberRecord]] = defaultdict(list)
    for record in panel.records:
        if record.record_id in selected and record.status == "VALID" and _resolver_key(record) in score_rows:
            grouped[_group_key(record)].append(record)
    context = _context_map(context_router)
    profiles = validation_profiles(observations)
    pairs = [
        _build_record(key, records, score_rows, context, profiles, max_members, confidence_floor)
        for key, records in sorted(grouped.items())
    ]
    if not pairs:
        raise DataQualityError("ensemble selection produced no evidence-backed records")
    records, selections = zip(*pairs, strict=True)
    output = EnsembleForecastPanel(records=tuple(records))
    confidence = {
        "records": [confidence_record(row, selection, effective_count=_effective_count) for row, selection in zip(records, selections, strict=True)],
        "confidence_semantics": "OOS_CALIBRATION_STABILITY_DISAGREEMENT_OOD_REGIME_COMPOSITE",
        "calibration_version": "RC34-CONFIDENCE-V3",
    }
    return output, confidence, {"records": list(selections)}


def _select_group(key, records, score_map, profiles, maximum):
    ordered = sorted(records, key=lambda row: (_loss(score_map[_resolver_key(row)]), row.resolver_id))
    resolver_ids = [row.resolver_id for row in ordered]
    aligned = aligned_matrix(
        profiles, resolver_ids, underlying=key[2], target_id=key[3], horizon=key[4], unit=key[5],
    )
    pairwise, mcs, contributions = [], {"resolver_ids": resolver_ids}, []
    if aligned is not None:
        predictions, realized, _ = aligned
        pairwise = pairwise_evidence(predictions, realized, resolver_ids)
        mcs = model_confidence_set(predictions, realized, resolver_ids)
        contributions = marginal_contributions(predictions, realized, resolver_ids)
    eligible = set(mcs.get("resolver_ids", resolver_ids))
    contribution_map = {row["resolver_id"]: row for row in contributions}
    selected, rejected = [], []
    for record in ordered:
        if record.resolver_id not in eligible:
            rejected.append({"record_id": record.record_id, "reason": "OUTSIDE_MODEL_CONFIDENCE_SET"})
            continue
        if len(selected) >= maximum:
            rejected.append({"record_id": record.record_id, "reason": "CANDIDATE_BUDGET"})
            continue
        redundancy = _pair_redundancy(record, selected, pairwise)
        same_family = any(item.resolver_family == record.resolver_family for item in selected)
        marginal = contribution_map.get(record.resolver_id, {}).get("marginal_contribution")
        if redundancy and same_family and (marginal is None or float(marginal) <= 0.0):
            rejected.append({"record_id": record.record_id, "reason": "RESIDUAL_REDUNDANCY_AND_REPLACEABILITY"})
            continue
        selected.append(record)
    return selected, {
        "rejected": rejected,
        "pairwise_residual_evidence": pairwise,
        "model_confidence_set": mcs,
        "marginal_contributions": contributions,
    }


def _build_record(key, records, score_rows, context, profiles, max_members, confidence_floor):
    members = sorted(records, key=lambda row: (_loss(score_rows[_resolver_key(row)]), row.resolver_id))[:max_members]
    weights, combiner, comparison, solver = _combination_state(key, members, score_rows, profiles)
    points = np.asarray([row.point_forecast for row in members], dtype=float)
    center = float(np.average(points, weights=weights))
    dispersion = float(np.sqrt(np.average((points - center) ** 2, weights=weights)))
    context_row = context.get(_economic_key(members[0]))
    if context_row is None or context_row.get("context_uncertainty") is None:
        raise DataQualityError("ensemble confidence requires calibrated context evidence")
    confidence, components, evidence_fraction, abstained = _confidence_state(
        members, score_rows, weights, dispersion, context_row, confidence_floor,
    )
    record = _ensemble_record(key, members, weights, combiner, center, dispersion, confidence, abstained)
    return record, {
        "record_id": record.record_id,
        "member_ids": record.member_ids,
        "weights": record.weights,
        "combiner": f"{combiner}_PROBABILISTIC_MIXTURE",
        "effective_ensemble_size": _effective_count(weights),
        "confidence": confidence,
        "confidence_components": components,
        "confidence_evidence_fraction": evidence_fraction,
        "missing_confidence_components": [name for name, value in components.items() if value is None],
        "abstained": abstained,
        "weighting_comparison": comparison,
        "stacking_solver": solver,
    }


def _combination_state(key, members, score_rows, profiles):
    inverse = _inverse_loss_weights(members, score_rows)
    weights, combiner, comparison = inverse, "INVERSE_VALIDATION_LOSS", {}
    solver = {"status": "NOT_ATTEMPTED"}
    aligned = aligned_matrix(
        profiles, [row.resolver_id for row in members],
        underlying=key[2], target_id=key[3], horizon=key[4], unit=key[5],
    )
    if aligned is not None and len(members) > 1:
        predictions, realized, _ = aligned
        stacking, solver = stacking_weights(predictions, realized)
        comparison = compare_weighting_schemes(predictions, realized, inverse, stacking)
        if comparison["selected"] == "NON_NEGATIVE_STACKING":
            weights, combiner = stacking, "NON_NEGATIVE_STACKING"
    return weights, combiner, comparison, solver


def _confidence_state(members, score_rows, weights, dispersion, context_row, confidence_floor):
    components = confidence_components(
        members, score_rows, weights, dispersion, context_row,
        resolver_key=_resolver_key, effective_count=_effective_count,
    )
    observed = [float(value) for value in components.values() if value is not None]
    if not observed:
        raise DataQualityError("ensemble confidence has no observable components")
    evidence_fraction = len(observed) / len(components)
    confidence = float((np.prod(observed) ** (1.0 / len(observed))) * evidence_fraction)
    uncertainty = float(context_row["context_uncertainty"])
    abstained = evidence_fraction < 1.0 or confidence < confidence_floor
    abstained = abstained or uncertainty >= 0.90 or context_row.get("recommended_action") == "ABSTAIN"
    return confidence, components, evidence_fraction, abstained


def _ensemble_record(key, members, weights, combiner, center, dispersion, confidence, abstained):
    first = members[0]
    return EnsembleForecastRecord(
        record_id=stable_id("ensemble", key, [row.record_id for row in members], weights.tolist(), combiner),
        as_of_time=first.as_of_time, prediction_timestamp=first.prediction_timestamp,
        underlying=first.underlying, target_id=first.target_id, horizon=first.horizon, unit=first.unit,
        distribution=_mixture_distribution(members, weights, center, dispersion),
        member_ids=tuple(row.record_id for row in members),
        weights=tuple(float(value) for value in weights), epistemic_uncertainty=dispersion,
        confidence=confidence, abstained=abstained,
        lineage_id=stable_id("ensemble-lineage", key, [row.lineage_id for row in members], combiner),
    )


def _mixture_distribution(members, weights, center, dispersion):
    components: list[MixtureComponent] = []
    exact = True
    for member, weight in zip(members, weights, strict=True):
        distribution = member.distribution
        if isinstance(distribution, ParametricDistribution):
            components.append(MixtureComponent(
                family=distribution.family,
                weight=float(weight),
                location=distribution.location,
                scale=distribution.scale,
                degrees_of_freedom=distribution.degrees_of_freedom,
                shape_parameter=distribution.shape_parameter,
            ))
        elif isinstance(distribution, MixtureDistribution):
            for item in distribution.components:
                components.append(item.model_copy(update={"weight": float(weight) * item.weight}))
        else:
            exact = False
            break
    if exact and 2 <= len(components) <= 8:
        total = sum(item.weight for item in components)
        normalized = tuple(item.model_copy(update={"weight": item.weight / total}) for item in components)
        return MixtureDistribution(components=normalized)
    samples: list[float] = []
    budget = 512
    for index, record in enumerate(members):
        count = max(1, int(round(float(weights[index]) * budget)))
        levels = (np.arange(count, dtype=float) + 0.5) / count
        samples.extend(quantile_value(record.distribution, float(level)) for level in levels)
    if dispersion > 0.0:
        samples.extend([center - 2.326 * dispersion, center, center + 2.326 * dispersion])
    return PointDistribution(value=center) if len(samples) < 2 else EmpiricalDistribution(samples=tuple(float(value) for value in samples[:2048]))


def _pair_redundancy(record, selected, evidence):
    if not selected:
        return False
    pairs = {(row["left_resolver_id"], row["right_resolver_id"]): row for row in evidence}
    for item in selected:
        key = tuple(sorted((record.resolver_id, item.resolver_id)))
        row = pairs.get(key)
        if row and float(row["absolute_residual_correlation"]) >= 0.95 and float(row["cofailure_rate"]) >= 0.10:
            return True
    scale = max(abs(record.point_forecast), *(abs(item.point_forecast) for item in selected), 1e-4)
    return any(abs(record.point_forecast - item.point_forecast) / scale < 1e-3 for item in selected)


def _score_map(scoring):
    return {
        _diagnostic_key(row): row for row in scoring.get("records", [])
        if row.get("status") == "OK" and int(row.get("sample_size", 0)) >= _MIN_OOF
    }


def _inverse_loss_weights(members, score_rows):
    inverse = np.asarray([1.0 / max(_loss(score_rows[_resolver_key(row)]), _EPS) for row in members], dtype=float)
    return inverse / np.sum(inverse)


def _loss(row):
    for name in ("crps_quantile_approx", "mse", "gaussian_log_score"):
        if row.get(name) is not None:
            value = float(row[name])
            return max(value, 1e-12) if name == "gaussian_log_score" else value
    raise DataQualityError("scoring row has no supported loss")


def _effective_count(weights):
    values = np.asarray(weights, dtype=float)
    total = float(np.sum(values))
    if total <= 0.0: return 0.0
    normalized = values / total
    return float(1.0 / np.sum(normalized**2))


def _resolver_key(record): return record.resolver_id, record.target_id, record.horizon, record.unit

def _economic_key(record): return record.underlying, record.target_id, record.horizon, record.unit

def _group_key(record): return record.as_of_time, record.prediction_timestamp, record.underlying, record.target_id, record.horizon, record.unit


def _diagnostic_key(row):
    required = ("resolver_id", "target_id", "horizon", "unit")
    if any(not str(row.get(name, "")).strip() for name in required):
        raise DataQualityError("scoring diagnostic lacks resolver/target/horizon/unit identity")
    return tuple(str(row[name]) for name in required)


def _serialized_group(key):
    return {"as_of_time": key[0].isoformat(), "prediction_timestamp": key[1].isoformat(), "underlying": str(key[2]), "target_id": str(key[3]), "horizon": str(key[4]), "unit": str(key[5])}

def _context_map(router):
    if not router:
        return {}
    result = {}
    for row in router.get("records", []):
        value = row.get("context_uncertainty")
        if value is not None and (not np.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0):
            raise DataQualityError("context_uncertainty must be finite and between zero and one")
        result[(row["underlying"], row["target_id"], row["horizon"], row["unit"])] = row
    return result
