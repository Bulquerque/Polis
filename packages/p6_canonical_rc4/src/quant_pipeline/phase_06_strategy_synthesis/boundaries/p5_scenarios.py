"""Economic adaptation of P5 RC34 distributions and paths into P6 beliefs."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from ..domain.enums import CapabilityStatus
from ..domain.models import (
    BeliefScenario,
    MarketBeliefState,
    P5ForecastConfidenceRecord,
    P5RegimeOODRecord,
    P5ReturnDistributionRecord,
    P5ScenarioPathRecord,
    UnderlyingObservation,
)
from ..foundation.contracts import parse_external_records
from ..foundation.errors import Phase6ContractError
from .p5_manifest import ValidatedP5Bundle
from .p5_distribution_adaptation import (
    _distribution_samples,
    _mass_audit,
    _normalize_scenario_mass,
    _scenario_distribution,
    _scenarios_from_distribution,
    _stratified_values,
)
from .p5_utils import horizon_days
from ..domain.market_price import reference_spot


def adapt_full_bundle(
    bundle: ValidatedP5Bundle,
    inputs: Mapping[str, Any],
    decision_time: datetime,
    module_id: str,
    *,
    max_distribution_scenarios: int,
) -> tuple[tuple[MarketBeliefState, ...], dict[str, str], tuple[str, ...]]:
    spots = _spot_map(inputs, decision_time, module_id)
    distribution_by_key = {
        (row.underlying, horizon_days(row.horizon)): row
        for row in bundle.distributions
    }
    confidence_by_key = {
        (row.underlying, horizon_days(row.horizon)): row
        for row in bundle.confidence
    }
    regime_by_key = {
        (row.underlying, horizon_days(row.horizon)): row
        for row in bundle.regime_ood
    }
    ambiguity_by_key = _ambiguity_index(bundle.ambiguity_sets)
    paths_by_key = _paths_index(bundle.scenario_paths)
    beliefs = []
    sources: dict[str, str] = {}
    reasons: list[str] = []
    for belief in bundle.compact_beliefs:
        adapted, source, belief_reasons = _adapt_belief(
            belief,
            bundle,
            spots,
            distribution_by_key,
            confidence_by_key,
            regime_by_key,
            ambiguity_by_key,
            paths_by_key,
            max_distribution_scenarios,
        )
        beliefs.append(adapted)
        sources[belief.underlying_id] = source
        reasons.extend(belief_reasons)
    return tuple(beliefs), sources, tuple(reasons)


def _adapt_belief(
    belief,
    bundle,
    spots,
    distributions,
    confidence,
    regime,
    ambiguity,
    paths,
    maximum,
):
    key = (belief.underlying_id, belief.horizon_days)
    confidence_row = confidence.get(key)
    regime_row = regime.get(key)
    ambiguity_row = ambiguity.get(key)
    scenarios, source, capability, mass_audit = _select_scenarios(
        belief,
        spots.get(belief.underlying_id),
        paths.get(key),
        distributions.get(key),
        maximum,
    )
    reason_codes = _capability_reasons(capability, confidence_row, regime_row, ambiguity_row, belief)
    ambiguity_ids = ()
    ambiguity_radius = None
    ambiguity_capability = belief.ambiguity_capability
    if ambiguity_row is not None:
        ambiguity_ids = ambiguity_row.plausible_distribution_ids + ambiguity_row.stress_distribution_ids
        ambiguity_radius = ambiguity_row.radius_or_band
        if not belief.ambiguity_probabilities:
            ambiguity_capability = CapabilityStatus.LIMITED
    updated = belief.model_copy(update={
        "scenarios": scenarios,
        "scenario_capability": capability,
        "confidence": belief.confidence if confidence_row is None else confidence_row.overall_confidence,
        "regime_context": _regime_context(belief.regime_context, regime_row),
        "ambiguity_capability": ambiguity_capability,
        "source_record_id": belief.source_artifact_id,
        "source_artifact_id": bundle.manifest.market_belief_state.artifact_id,
        "source_lineage_id": bundle.manifest.market_belief_state.metadata.get("lineage_id"),
        "source_manifest_id": bundle.manifest.artifact_id,
        "p5_contract_version": bundle.manifest.contract_version_for_receipt,
        "scenario_source": source,
        "scenario_mass_audit": mass_audit,
        "calibration_status": "UNAVAILABLE" if confidence_row is None else confidence_row.calibration_status,
        "abstained": None if confidence_row is None else confidence_row.abstained,
        "ood_severity": "UNAVAILABLE" if regime_row is None else regime_row.severity,
        "confidence_components": _confidence_components(confidence_row),
        "capability_reason_codes": tuple(sorted(set(reason_codes))),
        "ambiguity_distribution_ids": ambiguity_ids,
        "ambiguity_radius": ambiguity_radius,
    })
    return updated, source, reason_codes


def _select_scenarios(belief, spot, path_rows, distribution, maximum):
    if belief.scenarios:
        mass = sum((row.probability for row in belief.scenarios), Decimal("0"))
        return belief.scenarios, "NATIVE_MARKET_BELIEF", belief.scenario_capability, _mass_audit(
            method="NATIVE_MARKET_BELIEF", source_count=len(belief.scenarios), retained_count=len(belief.scenarios),
            original_mass=mass, retained_mass=mass, normalization_factor=Decimal("1"),
        )
    if spot is not None and path_rows:
        scenarios, audit = _scenarios_from_paths(path_rows, spot, include_audit=True)
        if scenarios:
            return scenarios, "P5_SCENARIO_PATHS", CapabilityStatus.AVAILABLE, audit
    if spot is not None and distribution is not None:
        scenarios, audit, source = _scenarios_from_distribution(distribution, spot, maximum, include_audit=True)
        if scenarios:
            return scenarios, source, CapabilityStatus.AVAILABLE, audit
    return (), "UNAVAILABLE", CapabilityStatus.LIMITED, _mass_audit(
        method="UNAVAILABLE", source_count=0, retained_count=0, original_mass=Decimal("0"),
        retained_mass=Decimal("0"), normalization_factor=None,
    )


def _spot_map(inputs: Mapping[str, Any], decision_time, module_id) -> dict[str, Decimal]:
    artifact = inputs.get("clean_underlying_trade_panel")
    if artifact is None:
        return {}
    records = parse_external_records(
        artifact,
        UnderlyingObservation,
        "clean_underlying_trade_panel",
        module_id,
    )
    output: dict[str, Decimal] = {}
    for record in records:
        if record.available_at > decision_time:
            raise Phase6ContractError(
                "P2 spot anchor is future dated",
                "P6_MARKET_CLOCK_MISMATCH",
                module_id,
                {"underlying_id": record.underlying_id},
            )
        output[record.underlying_id] = reference_spot(record)
    return output


def _paths_index(rows):
    output: dict[tuple[str, int], list[P5ScenarioPathRecord]] = defaultdict(list)
    for row in rows:
        if row.scenario_type == "NOMINAL":
            output[(row.underlying, horizon_days(row.horizon))].append(row)
    return output


def _ambiguity_index(rows):
    output = {}
    for row in rows:
        underlying = row.scope.get("underlying")
        horizon = row.scope.get("horizon")
        if underlying and horizon:
            output[(str(underlying), horizon_days(str(horizon)))] = row
    return output


def _scenarios_from_paths(rows, spot, *, include_audit: bool = False):
    grouped: dict[str, list[P5ScenarioPathRecord]] = defaultdict(list)
    for row in rows:
        grouped[row.scenario_id].append(row)
    output = []
    original_mass = Decimal("0")
    rejected_mass = Decimal("0")
    for scenario_id, path in sorted(grouped.items()):
        ordered = sorted(path, key=lambda row: row.path_step)
        probability = ordered[-1].probability
        if probability is None:
            continue
        original_mass += probability
        prices = tuple(
            row.future_spot if row.future_spot is not None else spot * (Decimal("1") + row.future_return)
            for row in ordered
        )
        if prices and all(price >= 0 for price in prices):
            output.append(BeliefScenario(
                scenario_id=scenario_id, terminal_underlying_price=prices[-1],
                probability=probability, path_prices=prices,
            ))
        else:
            rejected_mass += probability
    normalized, audit = _normalize_scenario_mass(
        tuple(output), method="P5_SCENARIO_PATHS", source_count=len(grouped),
        original_mass=original_mass, rejected_mass=rejected_mass, include_audit=True,
    )
    return (normalized, audit) if include_audit else normalized


def _confidence_components(record: P5ForecastConfidenceRecord | None):
    if record is None:
        return {}
    return {
        "calibration": record.calibration_component,
        "data_quality": record.data_quality_component,
        "model_stability": record.model_stability_component,
        "ensemble_disagreement": record.ensemble_disagreement_component,
        "ood": record.ood_component,
        "regime_uncertainty": record.regime_uncertainty_component,
    }


def _regime_context(original: str, record: P5RegimeOODRecord | None) -> str:
    if record is None:
        return original
    dominant = max(record.regime_probabilities, key=record.regime_probabilities.get, default="UNAVAILABLE")
    return f"{dominant}|OOD_{record.severity}|{record.validity_status}"


def _capability_reasons(capability, confidence, regime, ambiguity, belief):
    reasons = list(regime.reason_codes if regime else ())
    if confidence is not None and confidence.abstained:
        reasons.append("P5_ABSTAINED")
    if capability is not CapabilityStatus.AVAILABLE:
        reasons.append("P5_SCENARIOS_UNAVAILABLE")
    if ambiguity is not None and not belief.ambiguity_probabilities:
        reasons.append("P5_AMBIGUITY_DISTRIBUTIONS_UNRESOLVED")
    return reasons
