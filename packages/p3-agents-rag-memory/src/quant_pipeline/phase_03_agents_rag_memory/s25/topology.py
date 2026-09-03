"""Implementation of P3.S25.M03 — topology validation and graph materialization."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from .artifacts import (
    NextSocialGraph,
    RelationshipCandidatePanel,
    RelationshipDecisionRecord,
    RelationshipEdge,
    TopologyMetrics,
    UpdatedSocialGraph,
)
from .common import content_hash, derived_id, lineage_id, log_event, require_same_context
from .errors import S25ContractError, S25TopologyError
from .types import ChangeDecision, EligibilityStatus, SocialGraphConfig

M03 = "P3.S25.M03"


@dataclass(slots=True)
class _GraphWork:
    edges: list[RelationshipEdge]
    existing_keys: set[tuple[str, str, str]]
    existing_pairs: set[tuple[str, str]]
    applied: list[RelationshipDecisionRecord]
    rejected: list[RelationshipDecisionRecord]


def _validate(model: type[Any], value: Any, *, label: str) -> Any:
    try:
        return model.model_validate(value)
    except ValidationError as exc:
        raise S25ContractError(f"invalid {label}: {exc}") from exc


def _parse_inputs(
    updated_social_graph: Mapping[str, Any],
    relationship_candidate_panel: Mapping[str, Any],
    social_graph_config: Mapping[str, Any],
) -> tuple[UpdatedSocialGraph, RelationshipCandidatePanel, SocialGraphConfig]:
    graph = _validate(UpdatedSocialGraph, updated_social_graph, label="updated_social_graph")
    proposals = _validate(
        RelationshipCandidatePanel,
        relationship_candidate_panel,
        label="relationship_candidate_panel",
    )
    config = _validate(SocialGraphConfig, social_graph_config, label="social_graph_config")
    require_same_context(graph, proposals)
    return graph, proposals, config


def _adjacency(people: tuple[str, ...], edges: list[RelationshipEdge]) -> dict[str, set[str]]:
    result = {person: set() for person in people}
    for edge in edges:
        result[edge.source_person_id].add(edge.target_person_id)
        result[edge.target_person_id].add(edge.source_person_id)
    return result


def _component_count(adjacency: dict[str, set[str]]) -> int:
    unseen = set(adjacency)
    components = 0
    while unseen:
        components += 1
        queue: deque[str] = deque([min(unseen)])
        unseen.remove(queue[0])
        while queue:
            current = queue.popleft()
            for neighbour in sorted(adjacency[current]):
                if neighbour in unseen:
                    unseen.remove(neighbour)
                    queue.append(neighbour)
    return components


def topology_metrics(*, nodes: tuple[Any, ...], edges: list[RelationshipEdge]) -> TopologyMetrics:
    """Compute graph constraints on the undirected projection."""
    people = tuple(node.person_id for node in nodes)
    adjacency = _adjacency(people, edges)
    degrees = [len(adjacency[person]) for person in people]
    roles = {node.person_id: node.role_family for node in nodes}
    max_degree = max(degrees, default=0)
    return TopologyMetrics(
        node_count=len(people),
        edge_count=len(edges),
        min_degree=min(degrees, default=0),
        max_degree=max_degree,
        connected_components=_component_count(adjacency) if people else 0,
        bridge_edges_between_role_families=sum(
            roles[edge.source_person_id] != roles[edge.target_person_id] for edge in edges
        ),
        max_hub_share=max_degree / (len(people) - 1) if len(people) > 1 else 0.0,
    )


def _validate_edge_policy(edge: RelationshipEdge, config: SocialGraphConfig) -> None:
    if edge.relationship_type not in config.allowed_relationship_types:
        raise S25TopologyError(f"invalid relationship type: {edge.relationship_type}")
    lower, upper = config.domain_trust_range
    values = [edge.general_trust, *edge.trust_by_domain.values()]
    if any(not lower <= value <= upper for value in values):
        raise S25TopologyError("relationship trust outside configured bounds")


def _constraint_reasons(metrics: TopologyMetrics, config: SocialGraphConfig) -> list[str]:
    reasons: list[str] = []
    if metrics.max_degree > config.max_degree:
        reasons.append("max_degree_exceeded")
    if metrics.max_hub_share > config.max_hub_share:
        reasons.append("max_hub_share_exceeded")
    if metrics.connected_components > config.max_connected_components:
        reasons.append("max_connected_components_exceeded")
    return reasons


def _minimum_reasons(metrics: TopologyMetrics, config: SocialGraphConfig) -> list[str]:
    reasons: list[str] = []
    if metrics.node_count > 1 and metrics.min_degree < config.min_degree:
        reasons.append("min_degree_not_met")
    if metrics.bridge_edges_between_role_families < config.min_bridge_edges_between_role_families:
        reasons.append("minimum_bridge_edges_not_met")
    return reasons


def _proposal_reasons(
    proposal: Any,
    people: set[str],
    work: _GraphWork,
    config: SocialGraphConfig,
    *,
    cycle_id: int,
) -> list[str]:
    key = (proposal.source_person_id, proposal.target_person_id, proposal.relationship_type)
    pair = (proposal.source_person_id, proposal.target_person_id)
    checks = {
        "unknown_person": proposal.source_person_id not in people or proposal.target_person_id not in people,
        "self_edge": proposal.source_person_id == proposal.target_person_id,
        "relationship_type_forbidden": proposal.relationship_type not in config.allowed_relationship_types,
        "duplicate_edge": key in work.existing_keys,
        "parallel_relationship_forbidden": (
            not config.allow_parallel_relationship_types and pair in work.existing_pairs
        ),
        "invalid_effective_cycle": proposal.effective_cycle != cycle_id + 1,
        "missing_initial_trust": not proposal.initial_trust_by_domain,
    }
    return sorted(reason for reason, failed in checks.items() if failed)


def _new_edge(proposal: Any, *, as_of: Any) -> RelationshipEdge:
    edge_id = derived_id(
        "edge",
        proposal.source_person_id,
        proposal.target_person_id,
        proposal.relationship_type,
        proposal.effective_cycle,
    )
    trust = proposal.initial_trust_by_domain
    return RelationshipEdge(
        edge_id=edge_id,
        source_person_id=proposal.source_person_id,
        target_person_id=proposal.target_person_id,
        relationship_type=proposal.relationship_type,
        trust_by_domain=trust,
        general_trust=sum(trust.values()) / len(trust),
        interaction_count=proposal.interaction_count,
        last_observed_at=proposal.proposed_at,
        created_at=as_of,
        valid_from_cycle=proposal.effective_cycle,
        lineage_ids=proposal.lineage_ids,
    )


def _record_rejection(work: _GraphWork, proposal: Any, reasons: list[str]) -> None:
    work.rejected.append(
        RelationshipDecisionRecord(
            relationship_change_id=proposal.relationship_change_id,
            decision=ChangeDecision.REJECTED,
            reason_codes=tuple(sorted(reasons)),
        )
    )


def _apply_one(
    proposal: Any,
    graph: UpdatedSocialGraph,
    work: _GraphWork,
    config: SocialGraphConfig,
) -> None:
    reasons = _proposal_reasons(proposal, {n.person_id for n in graph.nodes}, work, config,
                                cycle_id=graph.cycle_id)
    if reasons:
        _record_rejection(work, proposal, reasons)
        return
    edge = _new_edge(proposal, as_of=graph.as_of_time)
    _validate_edge_policy(edge, config)
    topology_reasons = _constraint_reasons(
        topology_metrics(nodes=graph.nodes, edges=[*work.edges, edge]),
        config,
    )
    if topology_reasons:
        _record_rejection(work, proposal, topology_reasons)
        return
    work.edges.append(edge)
    work.existing_keys.add((edge.source_person_id, edge.target_person_id, edge.relationship_type))
    work.existing_pairs.add((edge.source_person_id, edge.target_person_id))
    work.applied.append(
        RelationshipDecisionRecord(
            relationship_change_id=proposal.relationship_change_id,
            decision=ChangeDecision.APPLIED,
            reason_codes=("all_constraints_satisfied",),
            edge_id=edge.edge_id,
        )
    )


def _apply_eligible(
    graph: UpdatedSocialGraph,
    proposals: RelationshipCandidatePanel,
    config: SocialGraphConfig,
) -> _GraphWork:
    edges = sorted(graph.records, key=lambda item: item.edge_id)
    work = _GraphWork(
        edges=list(edges),
        existing_keys={(e.source_person_id, e.target_person_id, e.relationship_type) for e in edges},
        existing_pairs={(e.source_person_id, e.target_person_id) for e in edges},
        applied=[],
        rejected=[],
    )
    eligible = sorted(
        (p for p in proposals.records if p.eligibility_status is EligibilityStatus.ELIGIBLE),
        key=lambda p: (p.source_person_id, p.relationship_type, p.target_person_id, p.relationship_change_id),
    )
    for proposal in eligible:
        _apply_one(proposal, graph, work, config)
    return work


def _build_output(
    graph: UpdatedSocialGraph,
    proposals: RelationshipCandidatePanel,
    work: _GraphWork,
    metrics: TopologyMetrics,
) -> NextSocialGraph:
    payload = {
        "schema_version": "p3.s25.next_social_graph.v2",
        "run_id": graph.run_id,
        "cycle_id": graph.cycle_id,
        "as_of_time": graph.as_of_time,
        "lineage_id": lineage_id(M03, "next_social_graph", (graph.lineage_id, proposals.lineage_id)),
        "directed": True,
        "nodes": graph.nodes,
        "records": tuple(sorted(work.edges, key=lambda item: item.edge_id)),
        "applied_changes": tuple(sorted(work.applied, key=lambda item: item.relationship_change_id)),
        "rejected_changes": tuple(sorted(work.rejected, key=lambda item: item.relationship_change_id)),
        "topology_metrics": metrics,
    }
    return NextSocialGraph(**payload, content_hash=content_hash(payload))


def validate_and_materialize_relationship_changes(
    *,
    updated_social_graph: Mapping[str, Any],
    relationship_candidate_panel: Mapping[str, Any],
    social_graph_config: Mapping[str, Any],
) -> NextSocialGraph:
    """Apply eligible proposals while enforcing graph invariants."""
    graph, proposals, config = _parse_inputs(
        updated_social_graph, relationship_candidate_panel, social_graph_config
    )
    log_event("module_started", module_id=M03, run_id=graph.run_id, cycle_id=graph.cycle_id)
    for edge in graph.records:
        _validate_edge_policy(edge, config)
    work = _apply_eligible(graph, proposals, config)
    metrics = topology_metrics(nodes=graph.nodes, edges=work.edges)
    reasons = _constraint_reasons(metrics, config)
    if config.enforce_minimums:
        reasons.extend(_minimum_reasons(metrics, config))
    if reasons:
        raise S25TopologyError(
            "final graph violates topology contract: " + ", ".join(sorted(reasons))
        )
    output = _build_output(graph, proposals, work, metrics)
    log_event("module_succeeded", module_id=M03, run_id=graph.run_id, cycle_id=graph.cycle_id,
              status="IMPLEMENTED_QUALIFIED_INTERNAL", output_record_count=len(output.records),
              applied_count=len(output.applied_changes), rejected_count=len(output.rejected_changes))
    return output
