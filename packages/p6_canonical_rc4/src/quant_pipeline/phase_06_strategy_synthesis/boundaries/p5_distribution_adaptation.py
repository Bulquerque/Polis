"""Distribution discretization and probability-mass audit for P5→P6."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

from ..domain.models import BeliefScenario
from ..foundation.hashing import stable_id


def _scenarios_from_distribution(record, spot, maximum, *, include_audit: bool = False):
    distribution = record.distribution
    kind = str(distribution.get("kind", "")).upper()
    if kind in {"SCENARIO", "SCENARIOS"}:
        scenarios, audit = _scenario_distribution(record, spot, include_audit=True)
        result = (scenarios, audit, "P5_RETURN_DISTRIBUTION_SCENARIOS")
        return result if include_audit else scenarios
    weighted = _distribution_weighted_points(record)
    if not weighted:
        audit = _mass_audit(
            method=f"UNSUPPORTED_{kind or 'UNKNOWN'}",
            source_count=0,
            retained_count=0,
            original_mass=Decimal("0"),
            retained_mass=Decimal("0"),
            normalization_factor=None,
        )
        result = ((), audit, "UNAVAILABLE")
        return result if include_audit else ()
    selected = _stratified_weighted_points(weighted, maximum)
    output = []
    original_mass = sum((probability for _, probability in selected), Decimal("0"))
    rejected_mass = Decimal("0")
    for index, (value, probability) in enumerate(selected):
        terminal = spot * (Decimal("1") + value)
        if terminal >= 0:
            output.append(BeliefScenario(
                scenario_id=stable_id("p5-distribution", record.lineage_id, index, value),
                terminal_underlying_price=terminal, probability=probability,
            ))
        else:
            rejected_mass += probability
    scenarios, audit = _normalize_scenario_mass(
        tuple(output),
        method=(
            f"P5_{kind}_QUANTILE_DISCRETIZATION"
            if kind not in {"POINT", "EMPIRICAL"}
            else f"P5_{kind}"
        ),
        source_count=len(selected),
        original_mass=original_mass,
        rejected_mass=rejected_mass,
        include_audit=True,
    )
    source = (
        "P5_RETURN_DISTRIBUTION"
        if kind in {"POINT", "EMPIRICAL"}
        else "P5_RETURN_DISTRIBUTION_QUANTILE_APPROXIMATION"
    )
    result = (scenarios, audit, source)
    return result if include_audit else scenarios


def _distribution_samples(distribution: Mapping[str, Any]) -> list[Decimal]:
    """Backward-compatible sample projection used by unit-level boundary tests."""
    kind = str(distribution.get("kind", "")).upper()
    if kind == "POINT" and distribution.get("value") is not None:
        return [Decimal(str(distribution["value"]))]
    if kind == "EMPIRICAL" and isinstance(distribution.get("samples"), list):
        return [Decimal(str(value)) for value in distribution["samples"] if value is not None]
    if kind in {"SCENARIO", "SCENARIOS"} and isinstance(distribution.get("scenarios"), list):
        return [
            Decimal(str(item["value"]))
            for item in distribution["scenarios"]
            if isinstance(item, Mapping) and item.get("value") is not None
        ]
    return []


def _stratified_values(values: list[Decimal], maximum: int) -> tuple[Decimal, ...]:
    """Deterministically retain representative ordered values."""
    if maximum <= 0 or not values:
        return ()
    if len(values) <= maximum:
        return tuple(values)
    if maximum == 1:
        return (values[len(values) // 2],)
    indexes = sorted({round(index * (len(values) - 1) / (maximum - 1)) for index in range(maximum)})
    return tuple(values[index] for index in indexes)


def _distribution_weighted_points(record) -> list[tuple[Decimal, Decimal]]:
    distribution = record.distribution
    kind = str(distribution.get("kind", "")).upper()
    if kind == "EMPIRICAL" and isinstance(distribution.get("samples"), list):
        values = [Decimal(str(value)) for value in distribution["samples"]]
        probability = Decimal("1") / Decimal(len(values)) if values else Decimal("0")
        return [(value, probability) for value in values]
    if kind == "POINT" and distribution.get("value") is not None:
        return [(Decimal(str(distribution["value"])), Decimal("1"))]
    quantiles = []
    for item in record.quantiles:
        if not isinstance(item, Mapping) or item.get("level") is None or item.get("value") is None:
            continue
        quantiles.append((Decimal(str(item["level"])), Decimal(str(item["value"]))))
    quantiles.sort(key=lambda item: item[0])
    if not quantiles:
        return []
    levels = [item[0] for item in quantiles]
    if levels[0] <= 0 or levels[-1] >= 1 or any(left >= right for left, right in zip(levels, levels[1:])):
        return []
    midpoints = [
        (left + right) / Decimal("2")
        for left, right in zip(levels, levels[1:])
    ]
    boundaries = [Decimal("0"), *midpoints, Decimal("1")]
    return [
        (quantiles[index][1], boundaries[index + 1] - boundaries[index])
        for index in range(len(quantiles))
    ]


def _scenario_distribution(record, spot, *, include_audit: bool = False):
    output = []
    original_mass = Decimal("0")
    rejected_mass = Decimal("0")
    source_count = 0
    for index, item in enumerate(record.distribution.get("scenarios", [])):
        if not isinstance(item, Mapping):
            continue
        value = item.get("value")
        probability = item.get("probability")
        if value is None or probability is None:
            continue
        source_count += 1
        probability_decimal = Decimal(str(probability))
        original_mass += probability_decimal
        terminal = spot * (Decimal("1") + Decimal(str(value)))
        if terminal >= 0:
            output.append(BeliefScenario(
                scenario_id=stable_id("p5-distribution", record.lineage_id, index),
                terminal_underlying_price=terminal, probability=probability_decimal,
            ))
        else:
            rejected_mass += probability_decimal
    normalized, audit = _normalize_scenario_mass(
        tuple(output), method="P5_SCENARIO_DISTRIBUTION", source_count=source_count,
        original_mass=original_mass, rejected_mass=rejected_mass, include_audit=True,
    )
    return (normalized, audit) if include_audit else normalized


def _stratified_weighted_points(
    values: list[tuple[Decimal, Decimal]],
    maximum: int,
) -> tuple[tuple[Decimal, Decimal], ...]:
    if len(values) <= maximum:
        return tuple(values)
    if maximum == 1:
        total = sum((weight for _, weight in values), Decimal("0"))
        mean = sum((value * weight for value, weight in values), Decimal("0")) / total
        return ((mean, total),)
    indexes = sorted({round(index * (len(values) - 1) / (maximum - 1)) for index in range(maximum)})
    selected = [values[index] for index in indexes]
    total = sum((weight for _, weight in selected), Decimal("0"))
    return tuple((value, weight / total) for value, weight in selected)


def _normalize_scenario_mass(
    scenarios,
    *,
    method: str = "UNSPECIFIED",
    source_count: int | None = None,
    original_mass: Decimal | None = None,
    rejected_mass: Decimal = Decimal("0"),
    include_audit: bool = False,
):
    scenario_tuple = tuple(scenarios)
    retained_mass = sum((row.probability for row in scenario_tuple), Decimal("0"))
    resolved_original_mass = retained_mass + rejected_mass if original_mass is None else original_mass
    resolved_source_count = len(scenario_tuple) if source_count is None else source_count
    if not scenario_tuple or retained_mass <= 0:
        normalized = ()
        audit = _mass_audit(
            method=method, source_count=resolved_source_count, retained_count=0,
            original_mass=resolved_original_mass, retained_mass=retained_mass, normalization_factor=None,
        )
        return (normalized, audit) if include_audit else normalized
    factor = Decimal("1") / retained_mass
    scaled = [row.probability * factor for row in scenario_tuple]
    # Decimal division can be repeating (for example 1 / 0.75). Force exact
    # conservation by assigning the residual to the final deterministic row.
    scaled[-1] = Decimal("1") - sum(scaled[:-1], Decimal("0"))
    normalized = tuple(
        row.model_copy(update={"probability": probability})
        for row, probability in zip(scenario_tuple, scaled, strict=True)
    )
    audit = _mass_audit(
        method=method, source_count=resolved_source_count, retained_count=len(scenario_tuple),
        original_mass=resolved_original_mass, retained_mass=retained_mass, normalization_factor=factor,
    )
    return (normalized, audit) if include_audit else normalized


def _mass_audit(*, method, source_count, retained_count, original_mass, retained_mass, normalization_factor):
    rejected = max(original_mass - retained_mass, Decimal("0"))
    return {
        "method": method, "source_scenario_count": source_count, "retained_scenario_count": retained_count,
        "original_probability_mass": original_mass, "retained_probability_mass": retained_mass,
        "rejected_probability_mass": rejected, "normalization_factor": normalization_factor,
        "renormalized": bool(normalization_factor is not None and normalization_factor != Decimal("1")),
    }


