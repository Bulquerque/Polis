"""Causal cascade reconstruction for P3.S27.M03."""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime

from .artifacts import artifact_kwargs
from .common import derived_id, require_not_future, require_same_context
from .errors import S27CausalityError, S27ContractError
from .statistics import hhi
from .types import (
    ActivationPanel,
    AggregationSemanticsConfig,
    CascadeDetail,
    CascadeMetricsPanel,
    CascadeMetricsRecord,
    EventType,
    MetricStatus,
    SocialDeliveryPanel,
    SocialToolAuditPanel,
    StimulusPanel,
)

MODULE_ID = "P3.S27.M03"
Group = tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class EventNode:
    event_id: str
    event_type: EventType
    parent_id: str | None
    occurred_at: datetime
    group: Group | None
    person_id: str | None
    sender_person_id: str | None
    receiver_person_id: str | None
    lineage_id: str


def _stimulus_nodes(panel: StimulusPanel) -> list[EventNode]:
    nodes = []
    for record in panel.records:
        require_not_future(record.available_at, as_of=panel.as_of_time, label="stimulus.available_at")
        nodes.append(EventNode(record.stimulus_id, EventType.STIMULUS, None, record.event_time,
                               (record.underlying_id, record.proposition_id, record.horizon), record.target_person_id,
                               None, None, record.lineage_id))
    return nodes


def _activation_nodes(panel: ActivationPanel) -> list[EventNode]:
    nodes = []
    for record in panel.records:
        require_not_future(record.scheduled_at, as_of=panel.as_of_time, label="activation.scheduled_at")
        parent = record.causal_parent_id or record.stimulus_id
        nodes.append(EventNode(record.activation_id, EventType.ACTIVATION, parent, record.scheduled_at,
                               (record.underlying_id, record.proposition_id, record.horizon), record.person_id,
                               None, None, record.lineage_id))
    return nodes


def _delivery_nodes(panel: SocialDeliveryPanel, config: AggregationSemanticsConfig) -> list[EventNode]:
    allowed = {status.value for status in config.causal_delivery_statuses}
    rank = {"SEEN": 1, "INTERPRETED": 2, "USED": 3}
    selected: dict[str, object] = {}
    for record in panel.records:
        require_not_future(record.status_at, as_of=panel.as_of_time, label="delivery.status_at")
        if record.status.value not in allowed:
            continue
        current = selected.get(record.message_id)
        if current is None or (rank.get(record.status.value, 0), record.status_at) > (rank.get(current.status.value, 0), current.status_at):
            selected[record.message_id] = record
    nodes = []
    for record in selected.values():
        group = None
        if record.underlying_id and record.proposition_id and record.horizon:
            group = (record.underlying_id, record.proposition_id, record.horizon)
        nodes.append(EventNode(record.message_id, EventType.SOCIAL_DELIVERY, record.causal_parent_id, record.status_at,
                               group, record.receiver_person_id, record.sender_person_id, record.receiver_person_id,
                               record.lineage_id))
    return nodes


def _social_tool_nodes(panel: SocialToolAuditPanel, config: AggregationSemanticsConfig) -> list[EventNode]:
    allowed = {status.value for status in config.validated_tool_statuses}
    nodes = []
    for record in panel.records:
        require_not_future(record.event_time, as_of=panel.as_of_time, label="social_tool.event_time")
        if record.execution_status.value not in allowed or not record.result_validated:
            continue
        nodes.append(EventNode(record.audit_id, EventType.SOCIAL_TOOL, record.causal_parent_id or record.message_id,
                               record.event_time, None, record.person_id, None, None, record.lineage_id))
    return nodes


def _unique(nodes: list[EventNode]) -> dict[str, EventNode]:
    output: dict[str, EventNode] = {}
    for node in nodes:
        if node.event_id in output:
            raise S27ContractError(f"duplicate causal event_id: {node.event_id}")
        output[node.event_id] = node
    return output


def _linked(nodes: dict[str, EventNode]) -> tuple[dict[str, EventNode], list[EventNode]]:
    linked: dict[str, EventNode] = {}
    unlinked: list[EventNode] = []
    for event_id, node in nodes.items():
        if node.event_type is EventType.STIMULUS:
            linked[event_id] = node
        elif node.parent_id is None or node.parent_id not in nodes:
            unlinked.append(node)
        else:
            linked[event_id] = node
    return linked, unlinked


def _topological(nodes: dict[str, EventNode]) -> list[str]:
    children: dict[str, list[str]] = defaultdict(list)
    indegree = {event_id: 0 for event_id in nodes}
    for event_id, node in nodes.items():
        if node.parent_id in nodes:
            children[node.parent_id].append(event_id)
            indegree[event_id] += 1
    queue = deque(sorted(event_id for event_id, degree in indegree.items() if degree == 0))
    order: list[str] = []
    while queue:
        current = queue.popleft()
        order.append(current)
        for child in sorted(children[current]):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if len(order) != len(nodes):
        raise S27CausalityError("causal event graph contains a cycle")
    return order


def _root_and_depth(event_id: str, nodes: dict[str, EventNode]) -> tuple[str | None, int]:
    seen: set[str] = set()
    current = nodes[event_id]
    depth = 0
    while current.parent_id in nodes:
        if current.event_id in seen:
            raise S27CausalityError("causal cycle detected")
        seen.add(current.event_id)
        current = nodes[current.parent_id]
        depth += 1
    if current.event_type is not EventType.STIMULUS:
        return None, depth
    return current.event_id, depth


def _cascade_detail(root_id: str, node_ids: list[str], nodes: dict[str, EventNode], config: AggregationSemanticsConfig) -> CascadeDetail:
    selected = [nodes[event_id] for event_id in node_ids]
    started = min(node.occurred_at for node in selected)
    ended = max(node.occurred_at for node in selected)
    duration = max(0.0, (ended - started).total_seconds())
    depths = [_root_and_depth(node.event_id, nodes)[1] for node in selected]
    social_types = {EventType.SOCIAL_DELIVERY, EventType.SOCIAL_TOOL}
    secondary = [node for node in selected if node.event_type is EventType.ACTIVATION and node.parent_id in nodes and nodes[node.parent_id].event_type in social_types]
    exposed = {node.receiver_person_id for node in selected if node.event_type is EventType.SOCIAL_DELIVERY and node.receiver_person_id}
    activated = {node.person_id for node in secondary if node.person_id}
    originators: Counter[str] = Counter()
    for activation in secondary:
        parent = nodes.get(activation.parent_id or "")
        if parent and parent.event_type is EventType.SOCIAL_DELIVERY and parent.sender_person_id:
            originators[parent.sender_person_id] += 1
    contagion = len(activated & exposed) / len(exposed) if exposed else 0.0
    return CascadeDetail(
        cascade_id=derived_id("cascade", root_id, *sorted(node_ids)), root_stimulus_id=root_id,
        size=len(selected), depth=max(depths), duration_seconds=duration,
        speed_events_per_second=(len(selected) - 1) / duration if duration > 0.0 else 0.0,
        secondary_activation_count=len(secondary), exposed_person_count=len(exposed),
        social_contagion=contagion, influence_concentration=hhi(tuple(originators.values())),
        started_at=started, ended_at=ended, node_ids=tuple(sorted(node_ids)),
    )



def _metric_records(
    *,
    groups: set[Group],
    details_by_group: dict[Group, list[CascadeDetail]],
    lineages_by_group: dict[Group, set[str]],
    unlinked_by_group: Counter[Group],
    causal_coverage: float,
    base_lineages: tuple[str, ...],
    as_of: datetime,
    formula_version: str,
) -> tuple[CascadeMetricsRecord, ...]:
    output: list[CascadeMetricsRecord] = []
    for group in sorted(groups):
        details = details_by_group.get(group, [])
        if not details:
            output.append(CascadeMetricsRecord(
                underlying_id=group[0], proposition_id=group[1], horizon=group[2], as_of_time=as_of,
                formula_version=formula_version, status=MetricStatus.NO_COVERAGE,
                cascade_count=0, mean_cascade_size=0.0, max_cascade_size=0, mean_cascade_depth=0.0,
                max_cascade_depth=0, mean_cascade_speed=0.0, mean_cascade_duration_seconds=0.0,
                secondary_activation_rate=0.0, social_contagion=0.0, influence_concentration=0.0,
                causal_coverage_ratio=causal_coverage, linked_event_count=0,
                unlinked_event_count=unlinked_by_group[group], cascades=(), input_lineage_ids=base_lineages,
            ))
            continue
        total_secondary = sum(item.secondary_activation_count for item in details)
        total_exposed = sum(item.exposed_person_count for item in details)
        all_lineages = tuple(sorted(set(base_lineages) | lineages_by_group[group]))
        output.append(CascadeMetricsRecord(
            underlying_id=group[0], proposition_id=group[1], horizon=group[2], as_of_time=as_of,
            formula_version=formula_version,
            status=MetricStatus.READY if unlinked_by_group[group] == 0 else MetricStatus.DEGRADED,
            cascade_count=len(details), mean_cascade_size=sum(item.size for item in details) / len(details),
            max_cascade_size=max(item.size for item in details),
            mean_cascade_depth=sum(item.depth for item in details) / len(details),
            max_cascade_depth=max(item.depth for item in details),
            mean_cascade_speed=sum(item.speed_events_per_second for item in details) / len(details),
            mean_cascade_duration_seconds=sum(item.duration_seconds for item in details) / len(details),
            secondary_activation_rate=total_secondary / total_exposed if total_exposed else 0.0,
            social_contagion=sum(item.social_contagion for item in details) / len(details),
            influence_concentration=sum(item.influence_concentration for item in details) / len(details),
            causal_coverage_ratio=causal_coverage, linked_event_count=sum(item.size for item in details),
            unlinked_event_count=unlinked_by_group[group], cascades=tuple(details), input_lineage_ids=all_lineages,
        ))
    return tuple(output)


def measure_cascades(*, activation_panel: ActivationPanel, stimulus_panel: StimulusPanel, social_delivery_panel: SocialDeliveryPanel, social_tool_audit_panel: SocialToolAuditPanel, aggregation_semantics_config: AggregationSemanticsConfig) -> CascadeMetricsPanel:
    run_id, cycle_id, as_of = require_same_context(activation_panel, stimulus_panel, social_delivery_panel, social_tool_audit_panel)
    all_nodes = _unique(_stimulus_nodes(stimulus_panel) + _activation_nodes(activation_panel) + _delivery_nodes(social_delivery_panel, aggregation_semantics_config) + _social_tool_nodes(social_tool_audit_panel, aggregation_semantics_config))
    linked, initially_unlinked = _linked(all_nodes)
    _topological(linked)
    cascades_by_root: dict[str, list[str]] = defaultdict(list)
    additional_unlinked: list[EventNode] = []
    for event_id in sorted(linked):
        root, _ = _root_and_depth(event_id, linked)
        (additional_unlinked if root is None else cascades_by_root[root]).append(linked[event_id] if root is None else event_id)
    unlinked = initially_unlinked + additional_unlinked
    details_by_group: dict[Group, list[CascadeDetail]] = defaultdict(list)
    lineages_by_group: dict[Group, set[str]] = defaultdict(set)
    for root_id, node_ids in cascades_by_root.items():
        root = linked[root_id]
        if root.group is None:
            raise S27CausalityError("root stimulus must define a metric group")
        for event_id in node_ids:
            node = linked[event_id]
            if node.group is not None and node.group != root.group:
                raise S27CausalityError("causal child group conflicts with root stimulus group")
            lineages_by_group[root.group].add(node.lineage_id)
        details_by_group[root.group].append(_cascade_detail(root_id, node_ids, linked, aggregation_semantics_config))
    unlinked_by_group: Counter[Group] = Counter(node.group for node in unlinked if node.group is not None)
    causal_coverage = len(linked) / len(all_nodes) if all_nodes else 0.0
    base_lineages = (activation_panel.lineage_id, stimulus_panel.lineage_id, social_delivery_panel.lineage_id, social_tool_audit_panel.lineage_id)
    records = _metric_records(
        groups=set(details_by_group) | set(unlinked_by_group), details_by_group=details_by_group,
        lineages_by_group=lineages_by_group, unlinked_by_group=unlinked_by_group,
        causal_coverage=causal_coverage, base_lineages=base_lineages, as_of=as_of,
        formula_version=aggregation_semantics_config.formula_version,
    )
    kwargs = artifact_kwargs(module_id=MODULE_ID, output_name="cascade_metrics_panel", schema_version="p3.s27.v1", run_id=run_id, cycle_id=cycle_id, as_of_time=as_of, lineages=base_lineages)
    return CascadeMetricsPanel(**kwargs, formula_version=aggregation_semantics_config.formula_version, records=records)
