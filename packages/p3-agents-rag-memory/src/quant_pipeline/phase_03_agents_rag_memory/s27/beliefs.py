"""Belief distribution aggregation for P3.S27.M01."""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from .artifacts import artifact_kwargs
from .common import require_not_future, require_same_context
from .errors import S27ContractError
from .statistics import effective_sample_size, normalized_entropy, weighted_mean, weighted_variance
from .types import (
    AggregationSemanticsConfig,
    BeliefDistributionPanel,
    BeliefDistributionRecord,
    BeliefStateRecord,
    MetricStatus,
    NextBeliefStatePanel,
    PropositionRegistryConfig,
    StimulusPanel,
    ValidatedPopulationManifest,
    validate_group,
)

MODULE_ID = "P3.S27.M01"
Group = tuple[str, str, str]


def _population_weights(population: ValidatedPopulationManifest) -> dict[str, float]:
    return {record.person_id: record.representation_weight for record in population.records}


def _runtime_engineeliefs(panel: NextBeliefStatePanel, population: dict[str, float], registry: PropositionRegistryConfig) -> dict[Group, list[BeliefStateRecord]]:
    grouped: dict[Group, list[BeliefStateRecord]] = defaultdict(list)
    seen: set[tuple[Group, str]] = set()
    for record in panel.records:
        validate_group(registry, record.proposition_id, record.horizon)
        if record.person_id not in population:
            raise S27ContractError(f"belief person is absent from population: {record.person_id}")
        require_not_future(record.changed_at, as_of=panel.as_of_time, label="belief.changed_at")
        key = (record.underlying_id, record.proposition_id, record.horizon)
        identity = (key, record.person_id)
        if identity in seen:
            raise S27ContractError(f"duplicate belief for person/group: {identity}")
        seen.add(identity)
        grouped[key].append(record)
    return grouped


def _stimulus_groups(panel: StimulusPanel, registry: PropositionRegistryConfig) -> set[Group]:
    groups: set[Group] = set()
    for record in panel.records:
        validate_group(registry, record.proposition_id, record.horizon)
        require_not_future(record.available_at, as_of=panel.as_of_time, label="stimulus.available_at")
        groups.add((record.underlying_id, record.proposition_id, record.horizon))
    return groups


def _direction_masses(records: list[BeliefStateRecord], weights: list[float], config: AggregationSemanticsConfig) -> tuple[float, float, float]:
    bearish = neutral = bullish = 0.0
    for record, weight in zip(records, weights, strict=True):
        if record.new_value <= config.bearish_threshold:
            bearish += weight
        elif record.new_value >= config.bullish_threshold:
            bullish += weight
        else:
            neutral += weight
    return bearish, neutral, bullish


def _probability(value: float) -> float:
    """Keep floating-point aggregation inside the declared probability domain."""

    return max(0.0, min(1.0, value))


def _polarization(records: list[BeliefStateRecord], weights: list[float], bearish: float, bullish: float) -> float:
    non_neutral = bearish + bullish
    total = sum(weights)
    if bearish <= 0.0 or bullish <= 0.0 or non_neutral <= 0.0:
        return 0.0
    positive_values = [record.new_value for record in records if record.new_value > 0.0]
    positive_weights = [weight for record, weight in zip(records, weights, strict=True) if record.new_value > 0.0]
    negative_values = [record.new_value for record in records if record.new_value < 0.0]
    negative_weights = [weight for record, weight in zip(records, weights, strict=True) if record.new_value < 0.0]
    if not positive_values or not negative_values:
        return 0.0
    separation = abs(weighted_mean(positive_values, positive_weights) - weighted_mean(negative_values, negative_weights)) / 2.0
    balance = 4.0 * bearish * bullish / (non_neutral**2)
    non_neutral_mass = non_neutral / total
    return max(0.0, min(1.0, separation * balance * non_neutral_mass))


def _dynamics(records: list[BeliefStateRecord], weights: list[float], config: AggregationSemanticsConfig) -> tuple[float | None, float | None, float]:
    velocities: list[float] = []
    velocity_weights: list[float] = []
    reversal_mass = 0.0
    reversal_eligible_mass = 0.0
    for record, weight in zip(records, weights, strict=True):
        if record.prior_updated_at is not None:
            elapsed = (record.changed_at - record.prior_updated_at).total_seconds()
            if elapsed >= config.velocity_min_elapsed_seconds:
                velocities.append(abs(record.delta) / (elapsed / timedelta(days=1).total_seconds()))
                velocity_weights.append(weight)
        if abs(record.prior_value) >= config.reversal_epsilon and abs(record.new_value) >= config.reversal_epsilon:
            reversal_eligible_mass += weight
            if record.prior_value * record.new_value < 0.0:
                reversal_mass += weight
    velocity = weighted_mean(velocities, velocity_weights) if velocities else None
    reversal = reversal_mass / reversal_eligible_mass if reversal_eligible_mass > 0.0 else None
    coverage = sum(velocity_weights) / sum(weights) if weights else 0.0
    return velocity, reversal, coverage


def _no_coverage(group: Group, *, as_of, formula_version: str, population_size: int, lineages: tuple[str, ...]) -> BeliefDistributionRecord:
    return BeliefDistributionRecord(
        underlying_id=group[0], proposition_id=group[1], horizon=group[2], as_of_time=as_of,
        formula_version=formula_version, status=MetricStatus.NO_COVERAGE, active_person_count=0,
        population_size=population_size, population_coverage_ratio=0.0, weight_coverage_ratio=0.0,
        effective_n=0.0, dynamics_coverage_ratio=0.0, input_lineage_ids=lineages,
    )


def aggregate_beliefs(*, next_belief_state_panel: NextBeliefStatePanel, validated_population_manifest: ValidatedPopulationManifest, stimulus_panel: StimulusPanel, proposition_registry_config: PropositionRegistryConfig, aggregation_semantics_config: AggregationSemanticsConfig) -> BeliefDistributionPanel:
    run_id, cycle_id, as_of = require_same_context(next_belief_state_panel, validated_population_manifest, stimulus_panel)
    population = _population_weights(validated_population_manifest)
    grouped = _runtime_engineeliefs(next_belief_state_panel, population, proposition_registry_config)
    groups = set(grouped) | _stimulus_groups(stimulus_panel, proposition_registry_config)
    total_population_weight = sum(population.values())
    base_lineages = (next_belief_state_panel.lineage_id, validated_population_manifest.lineage_id, stimulus_panel.lineage_id)
    output: list[BeliefDistributionRecord] = []
    for group in sorted(groups):
        records = grouped.get(group, [])
        if not records:
            output.append(_no_coverage(group, as_of=as_of, formula_version=aggregation_semantics_config.formula_version, population_size=len(population), lineages=base_lineages))
            continue
        weights = [population[record.person_id] * record.confidence for record in records]
        if sum(weights) <= 0.0:
            output.append(_no_coverage(group, as_of=as_of, formula_version=aggregation_semantics_config.formula_version, population_size=len(population), lineages=base_lineages))
            continue
        values = [record.new_value for record in records]
        bearish, neutral, bullish = _direction_masses(records, weights, aggregation_semantics_config)
        total = sum(weights)
        velocity, reversal, dynamics_coverage = _dynamics(records, weights, aggregation_semantics_config)
        genesis = all(
            record.prior_updated_at is None
            and abs(record.prior_value) < aggregation_semantics_config.reversal_epsilon
            for record in records
        )
        status = MetricStatus.READY if dynamics_coverage >= 1.0 or genesis else MetricStatus.DEGRADED
        lineages = tuple(sorted(set(base_lineages + tuple(record.lineage_id for record in records))))
        output.append(BeliefDistributionRecord(
            underlying_id=group[0], proposition_id=group[1], horizon=group[2], as_of_time=as_of,
            formula_version=aggregation_semantics_config.formula_version, status=status,
            active_person_count=len(records), population_size=len(population),
            population_coverage_ratio=len(records) / len(population) if population else 0.0,
            weight_coverage_ratio=sum(population[record.person_id] for record in records) / total_population_weight if total_population_weight else 0.0,
            effective_n=effective_sample_size(weights), belief_mean=weighted_mean(values, weights),
            belief_variance=weighted_variance(values, weights),
            belief_entropy=normalized_entropy((bearish, neutral, bullish)),
            belief_polarization=_polarization(records, weights, bearish, bullish),
            bullish_share=_probability(bullish / total), neutral_share=_probability(neutral / total), bearish_share=_probability(bearish / total),
            belief_update_velocity_per_day=velocity, belief_reversal_rate=reversal,
            dynamics_applicability="NOT_APPLICABLE_GENESIS" if genesis else "APPLICABLE",
            dynamics_coverage_ratio=dynamics_coverage, input_lineage_ids=lineages,
        ))
    kwargs = artifact_kwargs(module_id=MODULE_ID, output_name="belief_distribution_panel", schema_version="p3.s27.v1", run_id=run_id, cycle_id=cycle_id, as_of_time=as_of, lineages=base_lineages)
    return BeliefDistributionPanel(**kwargs, formula_version=aggregation_semantics_config.formula_version, records=tuple(output))
