"""Implementation of P3.S25.M01 — trust relationship updater."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeAlias

from pydantic import ValidationError

from .artifacts import (
    ActiveBeliefFeedbackBundle,
    CurrentSocialGraph,
    RelationshipEdge,
    SocialDeliveryPanel,
    TrustChange,
    UpdatedSocialGraph,
    ValidatedNextPersonStatePanel,
)
from .common import (
    clamp,
    derived_id,
    lineage_id,
    log_event,
    require_effective_cycle,
    require_not_future,
    require_same_context,
)
from .errors import S25ContractError, S25PolicyError
from .types import ExperienceType, FeedbackStatus, RelationshipUpdateConfig

M01 = "P3.S25.M01"


@dataclass(frozen=True, slots=True)
class _Experience:
    experience_id: str
    signal: float
    reliability: float
    weight: float
    observed_at: datetime
    lineage_id: str


ExperienceKey: TypeAlias = tuple[str, str, str, str]
ExperienceMap: TypeAlias = dict[ExperienceKey, list[_Experience]]


def _validate(model: type[Any], value: Any, *, label: str) -> Any:
    try:
        return model.model_validate(value)
    except ValidationError as exc:
        raise S25ContractError(f"invalid {label}: {exc}") from exc


def _edge_key(source: str, target: str, relationship_type: str) -> tuple[str, str, str]:
    return source, target, relationship_type


def _parse_inputs(
    current_social_graph: Mapping[str, Any],
    social_delivery_panel: Mapping[str, Any],
    validated_next_person_state_panel: Mapping[str, Any],
    active_belief_feedback_bundle: Mapping[str, Any],
    relationship_update_config: Mapping[str, Any],
) -> tuple[
    CurrentSocialGraph,
    SocialDeliveryPanel,
    ValidatedNextPersonStatePanel,
    ActiveBeliefFeedbackBundle,
    RelationshipUpdateConfig,
]:
    graph = _validate(CurrentSocialGraph, current_social_graph, label="current_social_graph")
    deliveries = _validate(SocialDeliveryPanel, social_delivery_panel, label="social_delivery_panel")
    states = _validate(
        ValidatedNextPersonStatePanel,
        validated_next_person_state_panel,
        label="validated_next_person_state_panel",
    )
    feedback = _validate(
        ActiveBeliefFeedbackBundle,
        active_belief_feedback_bundle,
        label="active_belief_feedback_bundle",
    )
    config = _validate(
        RelationshipUpdateConfig,
        relationship_update_config,
        label="relationship_update_config",
    )
    require_same_context(graph, deliveries, states, feedback)
    return graph, deliveries, states, feedback, config


def _validate_observation_policy(observation: Any, config: RelationshipUpdateConfig) -> None:
    if observation.domain not in config.trust_domains:
        raise S25PolicyError(f"unknown trust domain: {observation.domain}")
    if observation.relationship_type not in config.allowed_relationship_types:
        raise S25PolicyError("relationship type is not allowed")


def _validate_message_observation(
    observation: Any,
    delivery_by_id: dict[str, Any],
    config: RelationshipUpdateConfig,
    *,
    cycle_id: int,
    as_of: datetime,
) -> bool:
    if observation.source_message_id is None:
        return True
    delivery = delivery_by_id.get(observation.source_message_id)
    if delivery is None:
        raise S25ContractError("relationship observation references unknown message")
    if (
        delivery.sender_person_id != observation.counterparty_person_id
        or delivery.receiver_person_id != observation.observer_person_id
    ):
        raise S25ContractError("message direction does not match observation")
    if delivery.status not in config.allowed_delivery_statuses:
        return False
    require_not_future(delivery.status_at, as_of=as_of, label="delivery status")
    require_effective_cycle(delivery.effective_cycle, current_cycle=cycle_id, label="delivery")
    return True


def _collect_observations(
    graph: CurrentSocialGraph,
    deliveries: SocialDeliveryPanel,
    states: ValidatedNextPersonStatePanel,
    config: RelationshipUpdateConfig,
) -> ExperienceMap:
    grouped: ExperienceMap = defaultdict(list)
    delivery_by_id = {record.message_id: record for record in deliveries.records}
    edge_keys = {_edge_key(e.source_person_id, e.target_person_id, e.relationship_type) for e in graph.records}
    for state in states.records:
        for observation in state.relationship_observations:
            if observation.observer_person_id != state.person_id:
                raise S25ContractError("relationship observation is outside its person scope")
            require_not_future(observation.observed_at, as_of=graph.as_of_time, label="observation")
            require_effective_cycle(
                observation.effective_cycle,
                current_cycle=graph.cycle_id,
                label="observation",
            )
            _validate_observation_policy(observation, config)
            key = _edge_key(
                observation.observer_person_id,
                observation.counterparty_person_id,
                observation.relationship_type,
            )
            if key not in edge_keys or not _validate_message_observation(
                observation,
                delivery_by_id,
                config,
                cycle_id=graph.cycle_id,
                as_of=graph.as_of_time,
            ):
                continue
            weight = (
                config.direct_experience_weight
                if observation.experience_type is ExperienceType.DIRECT_EXPERIENCE
                else config.indirect_reputation_weight
            )
            grouped[(*key, observation.domain)].append(
                _Experience(
                    observation.observation_id,
                    observation.signal,
                    observation.reliability,
                    weight,
                    observation.observed_at,
                    observation.lineage_id,
                )
            )
    return grouped


def _collect_feedback(
    graph: CurrentSocialGraph,
    feedback: ActiveBeliefFeedbackBundle,
    config: RelationshipUpdateConfig,
    grouped: ExperienceMap,
) -> None:
    edge_keys = {_edge_key(e.source_person_id, e.target_person_id, e.relationship_type) for e in graph.records}
    for item in feedback.items:
        if item.status is not FeedbackStatus.MATURED:
            continue
        require_not_future(item.matured_at, as_of=graph.as_of_time, label="matured feedback")
        require_effective_cycle(
            item.effective_cycle,
            current_cycle=graph.cycle_id,
            label="matured feedback",
        )
        if item.domain not in config.trust_domains:
            raise S25PolicyError(f"unknown feedback trust domain: {item.domain}")
        key = _edge_key(item.observer_person_id, item.counterparty_person_id, item.relationship_type)
        if key not in edge_keys:
            continue
        grouped[(*key, item.domain)].append(
            _Experience(
                item.feedback_id,
                item.outcome_alignment,
                item.reliability,
                config.matured_feedback_weight,
                item.matured_at,
                item.lineage_id,
            )
        )


def _general_trust(edge: RelationshipEdge, config: RelationshipUpdateConfig) -> float:
    weighted = sum(
        config.domain_weights[domain]
        * edge.trust_by_domain.get(domain, config.new_domain_initial_trust)
        for domain in config.trust_domains
    )
    return clamp(weighted / sum(config.domain_weights.values()), 0.0, 1.0)


def _apply_domain(
    edge: RelationshipEdge,
    domain: str,
    experiences: list[_Experience],
    config: RelationshipUpdateConfig,
    *,
    cycle_id: int,
    as_of: datetime,
) -> tuple[float, TrustChange] | None:
    mass = sum(item.reliability * item.weight for item in experiences)
    if mass <= 0:
        return None
    normalized = sum(item.signal * item.reliability * item.weight for item in experiences) / mass
    old_value = edge.trust_by_domain.get(domain, config.new_domain_initial_trust)
    raw_delta = config.learning_rate * normalized
    applied_delta = clamp(raw_delta, -config.max_trust_delta_per_cycle, config.max_trust_delta_per_cycle)
    new_value = clamp(old_value + applied_delta, 0.0, 1.0)
    experience_ids = tuple(sorted(item.experience_id for item in experiences))
    input_lineage = tuple(sorted(item.lineage_id for item in experiences))
    change = TrustChange(
        change_id=derived_id("trustchg", edge.edge_id, domain, cycle_id, *experience_ids),
        edge_id=edge.edge_id,
        source_person_id=edge.source_person_id,
        target_person_id=edge.target_person_id,
        relationship_type=edge.relationship_type,
        domain=domain,
        old_value=old_value,
        normalized_signal=normalized,
        raw_delta=raw_delta,
        applied_delta=applied_delta,
        new_value=new_value,
        experience_ids=experience_ids,
        formula_version=config.formula_version,
        changed_at=as_of,
        lineage_ids=input_lineage,
    )
    return new_value, change


def _update_edge(
    edge: RelationshipEdge,
    grouped: ExperienceMap,
    config: RelationshipUpdateConfig,
    *,
    cycle_id: int,
    as_of: datetime,
) -> tuple[RelationshipEdge, list[TrustChange]]:
    trust = dict(edge.trust_by_domain)
    changes: list[TrustChange] = []
    used_experiences: list[_Experience] = []
    for domain in config.trust_domains:
        key = (*_edge_key(edge.source_person_id, edge.target_person_id, edge.relationship_type), domain)
        experiences = grouped.get(key, [])
        result = _apply_domain(edge, domain, experiences, config, cycle_id=cycle_id, as_of=as_of)
        if result is None:
            continue
        trust[domain], change = result
        changes.append(change)
        used_experiences.extend(experiences)
    last_observed = max((item.observed_at for item in used_experiences), default=edge.last_observed_at)
    lineage = tuple(sorted({*edge.lineage_ids, *(item.lineage_id for item in used_experiences)}))
    provisional = edge.model_copy(
        update={
            "trust_by_domain": trust,
            "interaction_count": edge.interaction_count + len(used_experiences),
            "last_observed_at": last_observed,
            "lineage_ids": lineage,
        }
    )
    return provisional.model_copy(update={"general_trust": _general_trust(provisional, config)}), changes


def update_trust_relationships(
    *,
    current_social_graph: Mapping[str, Any],
    social_delivery_panel: Mapping[str, Any],
    validated_next_person_state_panel: Mapping[str, Any],
    active_belief_feedback_bundle: Mapping[str, Any],
    relationship_update_config: Mapping[str, Any],
) -> UpdatedSocialGraph:
    """Update existing edge trust from observed and matured evidence only."""
    graph, deliveries, states, feedback, config = _parse_inputs(
        current_social_graph,
        social_delivery_panel,
        validated_next_person_state_panel,
        active_belief_feedback_bundle,
        relationship_update_config,
    )
    log_event("module_started", module_id=M01, run_id=graph.run_id, cycle_id=graph.cycle_id)
    grouped = _collect_observations(graph, deliveries, states, config)
    _collect_feedback(graph, feedback, config, grouped)
    results = [
        _update_edge(edge, grouped, config, cycle_id=graph.cycle_id, as_of=graph.as_of_time)
        for edge in sorted(graph.records, key=lambda value: value.edge_id)
    ]
    output = UpdatedSocialGraph(
        schema_version="p3.s25.updated_social_graph.v2",
        run_id=graph.run_id,
        cycle_id=graph.cycle_id,
        as_of_time=graph.as_of_time,
        lineage_id=lineage_id(M01, "updated_social_graph", (
            graph.lineage_id, deliveries.lineage_id, states.lineage_id, feedback.lineage_id
        )),
        directed=True,
        nodes=graph.nodes,
        records=tuple(edge for edge, _ in results),
        changes=tuple(sorted((change for _, changes in results for change in changes), key=lambda x: x.change_id)),
    )
    log_event("module_succeeded", module_id=M01, run_id=graph.run_id, cycle_id=graph.cycle_id,
              status="IMPLEMENTED_QUALIFIED_INTERNAL", output_record_count=len(output.records),
              trust_change_count=len(output.changes))
    return output
