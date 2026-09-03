"""Attention and information asymmetry metrics for P3.S27.M02."""
from __future__ import annotations

from collections import defaultdict

from .artifacts import artifact_kwargs
from .common import require_not_future, require_same_context
from .errors import S27ContractError
from .statistics import effective_sample_size, normalized_entropy, weighted_mean, weighted_standard_deviation
from .types import (
    AggregationSemanticsConfig,
    AttentionInformationMetrics,
    AttentionInformationRecord,
    MetricStatus,
    PersonEmergenceState,
    PersonToolEntitlementPanel,
    ToolCallAuditPanel,
    ValidatedNextPersonStatePanel,
    ValidatedPopulationManifest,
)

MODULE_ID = "P3.S27.M02"
Group = tuple[str, str, str]


def _population(population: ValidatedPopulationManifest) -> dict[str, float]:
    return {record.person_id: record.representation_weight for record in population.records}


def _states(panel: ValidatedNextPersonStatePanel, population: dict[str, float]) -> dict[Group, dict[str, PersonEmergenceState]]:
    grouped: dict[Group, dict[str, PersonEmergenceState]] = defaultdict(dict)
    for person in panel.records:
        if person.person_id not in population:
            raise S27ContractError(f"person state is absent from population: {person.person_id}")
        for state in person.emergence_states:
            require_not_future(state.updated_at, as_of=panel.as_of_time, label="emergence_state.updated_at")
            group = (state.underlying_id, state.proposition_id, state.horizon)
            if person.person_id in grouped[group]:
                raise S27ContractError(f"duplicate emergence state for {person.person_id}/{group}")
            grouped[group][person.person_id] = state
    return grouped


def _validated_tool_gains(panel: ToolCallAuditPanel, config: AggregationSemanticsConfig) -> dict[tuple[Group, str], tuple[float, tuple[str, ...], int]]:
    allowed = {status.value for status in config.validated_tool_statuses}
    gains: dict[tuple[Group, str], list[tuple[float, str]]] = defaultdict(list)
    for record in panel.records:
        require_not_future(record.executed_at, as_of=panel.as_of_time, label="tool_call.executed_at")
        if record.execution_status.value not in allowed or not record.result_validated:
            continue
        group = (record.underlying_id, record.proposition_id, record.horizon)
        gains[(group, record.person_id)].append((record.information_gain, record.lineage_id))
    output: dict[tuple[Group, str], tuple[float, tuple[str, ...], int]] = {}
    for key, items in gains.items():
        output[key] = (min(config.validated_tool_gain_cap, sum(item[0] for item in items)), tuple(sorted({item[1] for item in items})), len(items))
    return output


def _entitled(panel: PersonToolEntitlementPanel, group: Group, person_id: str) -> bool:
    for record in panel.records:
        if record.person_id != person_id or not record.entitled:
            continue
        if record.underlying_id not in (None, group[0]):
            continue
        if record.proposition_id not in (None, group[1]):
            continue
        if record.horizon not in (None, group[2]):
            continue
        return True
    return False


def _concentration(attention: list[float], weights: list[float]) -> float:
    masses = [score * weight for score, weight in zip(attention, weights, strict=True)]
    if sum(masses) <= 0.0:
        return 0.0
    return 1.0 - normalized_entropy(masses)


def measure_attention_information(*, validated_next_person_state_panel: ValidatedNextPersonStatePanel, tool_call_audit_panel: ToolCallAuditPanel, person_tool_entitlement_panel: PersonToolEntitlementPanel, validated_population_manifest: ValidatedPopulationManifest, aggregation_semantics_config: AggregationSemanticsConfig) -> AttentionInformationMetrics:
    run_id, cycle_id, as_of = require_same_context(validated_next_person_state_panel, tool_call_audit_panel, person_tool_entitlement_panel, validated_population_manifest)
    population = _population(validated_population_manifest)
    states = _states(validated_next_person_state_panel, population)
    tool_gains = _validated_tool_gains(tool_call_audit_panel, aggregation_semantics_config)
    groups = set(states) | {key[0] for key in tool_gains}
    base_lineages = (validated_next_person_state_panel.lineage_id, tool_call_audit_panel.lineage_id, person_tool_entitlement_panel.lineage_id, validated_population_manifest.lineage_id)
    output: list[AttentionInformationRecord] = []
    for group in sorted(groups):
        people = states.get(group, {})
        if not people:
            output.append(AttentionInformationRecord(
                underlying_id=group[0], proposition_id=group[1], horizon=group[2], as_of_time=as_of,
                formula_version=aggregation_semantics_config.formula_version, status=MetricStatus.NO_COVERAGE,
                active_person_count=0, population_size=len(population), population_coverage_ratio=0.0,
                effective_n=0.0, entitlement_coverage_ratio=0.0, executed_tool_coverage_ratio=0.0,
                validated_tool_call_count=0, input_lineage_ids=base_lineages,
            ))
            continue
        person_ids = sorted(people)
        weights = [population[person_id] for person_id in person_ids]
        attention = [people[person_id].attention_score for person_id in person_ids]
        info_scores: list[float] = []
        entitled_mass = executed_mass = 0.0
        call_count = 0
        lineages = set(base_lineages)
        for person_id, weight in zip(person_ids, weights, strict=True):
            state = people[person_id]
            gain, tool_lineages, calls = tool_gains.get((group, person_id), (0.0, (), 0))
            info = (
                aggregation_semantics_config.information_access_weight * state.information_access_score
                + aggregation_semantics_config.research_depth_weight * state.research_depth
                + aggregation_semantics_config.validated_tool_weight * gain
            )
            info_scores.append(max(0.0, min(1.0, info)))
            if _entitled(person_tool_entitlement_panel, group, person_id):
                entitled_mass += weight
            if calls > 0:
                executed_mass += weight
            call_count += calls
            lineages.add(state.lineage_id)
            lineages.update(tool_lineages)
        total_weight = sum(weights)
        output.append(AttentionInformationRecord(
            underlying_id=group[0], proposition_id=group[1], horizon=group[2], as_of_time=as_of,
            formula_version=aggregation_semantics_config.formula_version, status=MetricStatus.READY,
            active_person_count=len(person_ids), population_size=len(population),
            population_coverage_ratio=len(person_ids) / len(population) if population else 0.0,
            effective_n=effective_sample_size(weights), attention_intensity=weighted_mean(attention, weights),
            attention_concentration=_concentration(attention, weights),
            mean_information_access_score=weighted_mean(info_scores, weights),
            information_asymmetry=weighted_standard_deviation(info_scores, weights),
            entitlement_coverage_ratio=max(0.0, min(1.0, entitled_mass / total_weight)),
            executed_tool_coverage_ratio=max(0.0, min(1.0, executed_mass / total_weight)),
            validated_tool_call_count=call_count, input_lineage_ids=tuple(sorted(lineages)),
        ))
    kwargs = artifact_kwargs(module_id=MODULE_ID, output_name="attention_information_metrics", schema_version="p3.s27.v1", run_id=run_id, cycle_id=cycle_id, as_of_time=as_of, lineages=base_lineages)
    return AttentionInformationMetrics(**kwargs, formula_version=aggregation_semantics_config.formula_version, records=tuple(output))
