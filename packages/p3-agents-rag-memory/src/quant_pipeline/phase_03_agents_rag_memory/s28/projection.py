"""Tag-conditioned projection for P3.S28.M01."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .artifacts import artifact_kwargs
from .common import require_not_future, require_same_context
from .errors import S28ContractError
from .statistics import effective_sample_size, weighted_mean, weighted_population_std, weighted_variance
from .types import (
    BeliefStateRecord,
    MetricStatus,
    NextBeliefStatePanel,
    PersonSeedPanel,
    PersonalityTagRegistry,
    ProjectionStatus,
    PropositionRegistryConfig,
    S28AggregationSemanticsConfig,
    TagAssignment,
    TagProjectionPanel,
    TagProjectionRecord,
    TagProjectionSummaryRecord,
    ValidatedNextPersonStatePanel,
    ValidatedPopulationManifest,
)

MODULE_ID = "P3.S28.M01"
Group = tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class PersonBelief:
    person_id: str
    value: float
    base_weight: float
    lineage_id: str
    institution_type: str | None
    assignments: tuple[TagAssignment, ...]


def _validate_people(
    seeds: PersonSeedPanel,
    population: ValidatedPopulationManifest,
    states: ValidatedNextPersonStatePanel,
) -> tuple[dict[str, object], dict[str, object], set[str]]:
    seed_map = {item.person_id: item for item in seeds.records}
    population_map = {item.person_id: item for item in population.records}
    state_ids = {item.person_id for item in states.records}
    if set(seed_map) != set(population_map):
        raise S28ContractError("person_seed_panel and population manifest must contain identical person IDs")
    if not state_ids.issubset(population_map):
        raise S28ContractError("person state contains a person outside the frozen population")
    return seed_map, population_map, state_ids


def _validate_assignments(seeds: PersonSeedPanel, registry: PersonalityTagRegistry) -> None:
    categories = registry.tag_categories()
    for person in seeds.records:
        for assignment in person.tags:
            expected = categories.get(assignment.tag_id)
            if expected is None:
                raise S28ContractError(f"unknown tag_id: {assignment.tag_id}")
            if expected != assignment.category_id:
                raise S28ContractError(f"tag category mismatch for {assignment.tag_id}")


def _group_people(
    beliefs: NextBeliefStatePanel,
    seeds: dict[str, object],
    population: dict[str, object],
    states: ValidatedNextPersonStatePanel,
    registry: PropositionRegistryConfig,
) -> dict[Group, list[PersonBelief]]:
    state_grains = {
        (item.person_id, state.underlying_id, state.proposition_id, state.horizon)
        for item in states.records
        for state in item.emergence_states
    }
    grouped: dict[Group, list[PersonBelief]] = defaultdict(list)
    seen: set[tuple[Group, str]] = set()
    for belief in beliefs.records:
        registry.validate_grain(belief.proposition_id, belief.horizon)
        if belief.person_id not in population or belief.person_id not in seeds:
            raise S28ContractError(f"belief person is absent from frozen population: {belief.person_id}")
        grain = (belief.underlying_id, belief.proposition_id, belief.horizon)
        if (belief.person_id, *grain) not in state_grains:
            raise S28ContractError(f"belief has no matching person emergence state: {belief.person_id}/{grain}")
        key = (grain, belief.person_id)
        if key in seen:
            raise S28ContractError(f"duplicate belief for person and grain: {key}")
        seen.add(key)
        seed = seeds[belief.person_id]
        population_record = population[belief.person_id]
        grouped[grain].append(
            PersonBelief(
                person_id=belief.person_id,
                value=belief.new_value,
                base_weight=population_record.representation_weight * belief.confidence,
                lineage_id=belief.lineage_id,
                institution_type=population_record.institution_type or seed.institution_type,
                assignments=seed.tags,
            )
        )
    return grouped


def _tag_map(people: list[PersonBelief]) -> dict[tuple[str, str], list[tuple[PersonBelief, TagAssignment]]]:
    result: dict[tuple[str, str], list[tuple[PersonBelief, TagAssignment]]] = defaultdict(list)
    for person in people:
        for assignment in person.assignments:
            if assignment.effective_value > 0.0 and person.base_weight > 0.0:
                result[(assignment.category_id, assignment.tag_id)].append((person, assignment))
    return result


def _projection_record(
    grain: Group,
    as_of,
    population_size: int,
    people: list[PersonBelief],
    category_id: str,
    tag_id: str,
    members: list[tuple[PersonBelief, TagAssignment]],
    config: S28AggregationSemanticsConfig,
    shared_lineages: tuple[str, ...],
) -> TagProjectionRecord:
    base_total = sum(person.base_weight for person in people)
    member_ids = {person.person_id for person, _ in members}
    member_base_weights = [person.base_weight for person, _ in members]
    weights = [person.base_weight * assignment.intensity * assignment.confidence for person, assignment in members]
    values = [person.value for person, _ in members]
    raw_count = len(member_ids)
    effective_n = effective_sample_size(weights)
    ready = raw_count >= config.tag_projection_min_raw_person_count and effective_n + 1e-9 >= config.tag_projection_min_effective_n
    status = ProjectionStatus.READY if ready else ProjectionStatus.SUPPRESSED_SMALL_COHORT
    population_mean = weighted_mean([item.value for item in people], [item.base_weight for item in people])
    complement = [item for item in people if item.person_id not in member_ids]
    complement_weights = [item.base_weight for item in complement]
    complement_ready = (
        len(complement) >= config.tag_projection_min_raw_person_count
        and effective_sample_size(complement_weights) + 1e-9 >= config.tag_projection_min_effective_n
    )
    belief_mean = weighted_mean(values, weights) if ready else None
    belief_variance = weighted_variance(values, weights, belief_mean) if ready and belief_mean is not None else None
    complement_mean = weighted_mean([item.value for item in complement], complement_weights) if complement_ready else None
    confidence_weights = [person.base_weight * assignment.intensity for person, assignment in members]
    cohort_confidence = weighted_mean([assignment.confidence for _, assignment in members], confidence_weights) if sum(confidence_weights) > 0 else None
    lineages = sorted({*shared_lineages, *(person.lineage_id for person, _ in members)})
    return TagProjectionRecord(
        underlying_id=grain[0], proposition_id=grain[1], horizon=grain[2], as_of_time=as_of,
        formula_version=config.formula_version, category_id=category_id, tag_id=tag_id, status=status,
        raw_person_count=raw_count, population_size=population_size,
        population_coverage_ratio=raw_count / population_size if population_size else 0.0,
        weight_coverage_ratio=sum(member_base_weights) / base_total if base_total else 0.0,
        effective_n=effective_n, cohort_weight_sum=sum(weights), cohort_confidence=cohort_confidence,
        belief_mean=belief_mean, belief_variance=belief_variance, population_belief_mean=population_mean if ready else None,
        shift_vs_population=abs(belief_mean - population_mean) if belief_mean is not None else None,
        complement_belief_mean=complement_mean,
        divergence_vs_complement=abs(belief_mean - complement_mean) if belief_mean is not None and complement_mean is not None else None,
        input_lineage_ids=tuple(lineages),
    )


def _cohort_mean(people: list[PersonBelief], selected: set[str], config: S28AggregationSemanticsConfig) -> tuple[float | None, float, float]:
    members = [item for item in people if item.person_id in selected]
    weights = [item.base_weight for item in members]
    eff_n = effective_sample_size(weights)
    if len(members) < config.tag_projection_min_raw_person_count or eff_n + 1e-9 < config.tag_projection_min_effective_n:
        return None, eff_n, sum(weights)
    return weighted_mean([item.value for item in members], weights), eff_n, sum(weights)


def _expert_divergence(people: list[PersonBelief], config: S28AggregationSemanticsConfig) -> float | None:
    expert_ids = {
        person.person_id
        for person in people
        if any(item.tag_id in config.expert_tag_ids and item.effective_value >= config.expert_min_assignment_value for item in person.assignments)
    }
    nonexpert_ids = {person.person_id for person in people} - expert_ids
    expert_mean, _, _ = _cohort_mean(people, expert_ids, config)
    nonexpert_mean, _, _ = _cohort_mean(people, nonexpert_ids, config)
    if expert_mean is None or nonexpert_mean is None:
        return None
    return abs(expert_mean - nonexpert_mean)


def _institutional_disagreement(people: list[PersonBelief], config: S28AggregationSemanticsConfig) -> float | None:
    groups: dict[str, set[str]] = defaultdict(set)
    for person in people:
        if person.institution_type:
            groups[person.institution_type].add(person.person_id)
    means: list[float] = []
    weights: list[float] = []
    for person_ids in groups.values():
        mean, eff_n, total_weight = _cohort_mean(people, person_ids, config)
        if mean is not None and eff_n >= config.institutional_min_effective_n:
            means.append(mean)
            weights.append(total_weight)
    if len(means) < 2:
        return None
    return weighted_population_std(means, weights)


def _summary(
    grain: Group,
    as_of,
    people: list[PersonBelief],
    records: list[TagProjectionRecord],
    config: S28AggregationSemanticsConfig,
    shared_lineages: tuple[str, ...],
) -> TagProjectionSummaryRecord:
    ready = [item for item in records if item.status == ProjectionStatus.READY]
    if not ready:
        status = ProjectionStatus.NO_COVERAGE
    else:
        status = ProjectionStatus.READY
    expert = _expert_divergence(people, config)
    institutional = _institutional_disagreement(people, config)
    by_divergence = [item for item in ready if item.divergence_vs_complement is not None]
    by_shift = [item for item in ready if item.shift_vs_population is not None]
    top_divergence = max(by_divergence, key=lambda item: (item.divergence_vs_complement, item.tag_id), default=None)
    top_shift = max(by_shift, key=lambda item: (item.shift_vs_population, item.tag_id), default=None)
    lineages = sorted({*shared_lineages, *(item for record in records for item in record.input_lineage_ids)})
    return TagProjectionSummaryRecord(
        underlying_id=grain[0], proposition_id=grain[1], horizon=grain[2], as_of_time=as_of,
        formula_version=config.formula_version, status=status,
        expert_nonexpert_divergence=expert, institutional_disagreement=institutional,
        expert_nonexpert_applicability="APPLICABLE" if expert is not None else "NOT_APPLICABLE_INSUFFICIENT_COHORTS",
        institutional_applicability="APPLICABLE" if institutional is not None else "NOT_APPLICABLE_INSUFFICIENT_COHORTS",
        top_tag_divergence=top_divergence.divergence_vs_complement if top_divergence else None,
        top_tag_divergence_id=top_divergence.tag_id if top_divergence else None,
        top_tag_conditioned_shift=top_shift.shift_vs_population if top_shift else None,
        top_tag_conditioned_shift_id=top_shift.tag_id if top_shift else None,
        active_tag_projection_count=len(ready),
        suppressed_tag_projection_count=sum(item.status == ProjectionStatus.SUPPRESSED_SMALL_COHORT for item in records),
        input_lineage_ids=tuple(lineages),
    )


def project_tags(
    *,
    next_belief_state_panel: NextBeliefStatePanel,
    person_seed_panel: PersonSeedPanel,
    validated_population_manifest: ValidatedPopulationManifest,
    validated_next_person_state_panel: ValidatedNextPersonStatePanel,
    personality_tag_registry: PersonalityTagRegistry,
    proposition_registry_config: PropositionRegistryConfig,
    aggregation_semantics_config: S28AggregationSemanticsConfig,
) -> TagProjectionPanel:
    run_id, cycle_id, as_of = require_same_context(
        next_belief_state_panel, person_seed_panel, validated_population_manifest, validated_next_person_state_panel
    )
    for belief in next_belief_state_panel.records:
        require_not_future(belief.changed_at, as_of=as_of, label="belief.changed_at")
    seed_map, population_map, _ = _validate_people(person_seed_panel, validated_population_manifest, validated_next_person_state_panel)
    _validate_assignments(person_seed_panel, personality_tag_registry)
    grouped = _group_people(next_belief_state_panel, seed_map, population_map, validated_next_person_state_panel, proposition_registry_config)
    shared_lineages = (
        next_belief_state_panel.lineage_id, person_seed_panel.lineage_id, validated_population_manifest.lineage_id,
        validated_next_person_state_panel.lineage_id, personality_tag_registry.lineage_id or personality_tag_registry.registry_id,
    )
    records: list[TagProjectionRecord] = []
    summaries: list[TagProjectionSummaryRecord] = []
    for grain in sorted(grouped):
        people = grouped[grain]
        tag_members = _tag_map(people)
        if len(tag_members) > aggregation_semantics_config.max_active_tag_projections_per_grain:
            raise S28ContractError("active tag projection count exceeds configured maximum")
        group_records = [
            _projection_record(grain, as_of, len(validated_population_manifest.records), people, category, tag, members, aggregation_semantics_config, shared_lineages)
            for (category, tag), members in sorted(tag_members.items())
        ]
        records.extend(group_records)
        summaries.append(_summary(grain, as_of, people, group_records, aggregation_semantics_config, shared_lineages))
    kwargs = artifact_kwargs(
        module_id=MODULE_ID, output_name="tag_projection_panel", schema_version="p3.s28.v1",
        run_id=run_id, cycle_id=cycle_id, as_of_time=as_of, lineages=shared_lineages,
    )
    return TagProjectionPanel(**kwargs, formula_version=aggregation_semantics_config.formula_version, records=tuple(records), summaries=tuple(summaries))
