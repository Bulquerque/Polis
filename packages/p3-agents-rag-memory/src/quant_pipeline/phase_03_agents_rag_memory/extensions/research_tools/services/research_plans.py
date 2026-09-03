"""Research plan DAG registry and readiness resolution for P3.S34.M03."""

from __future__ import annotations

from collections import defaultdict

from ..contracts.artifacts import (
    ArtifactStatus,
    CanonicalToolOperationRegistry,
    ResearchModeRegistry,
)
from ..contracts.boundary_artifacts import Phase2ResearchViewReadinessReport, ReadinessStatus as ViewReadiness
from ..contracts.capability_artifacts import (
    ReadinessStatus,
    ResearchCapabilityTaxonomy,
    ResearchPlanDependencyMatrix,
    ResearchPlanDependencyRecord,
    ResearchPlanNode,
    ResearchPlanReadinessRecord,
    ResearchPlanReadinessReport,
    ResearchPlanRegistry,
    ResearchPlanTemplate,
)
from ..contracts.capability_configs import ResearchPlanRegistryConfig
from ..core.errors import fail
from .artifact_construction import finalize, lineage


def _topological_order(plan_id: str, node_ids: set[str], predecessors: dict[str, tuple[str, ...]]) -> list[str]:
    incoming = {node: set(predecessors[node]) for node in node_ids}
    for node, values in incoming.items():
        unknown = sorted(values - node_ids)
        if unknown:
            raise fail("P3RT-CONTRACT-3420", "plan node has unknown predecessor", {"plan_id": plan_id, "node_id": node, "predecessors": unknown})
    order: list[str] = []
    ready = sorted(node for node, values in incoming.items() if not values)
    while ready:
        node = ready.pop(0)
        order.append(node)
        for candidate in sorted(node_ids - set(order)):
            incoming[candidate].discard(node)
            if not incoming[candidate] and candidate not in ready:
                ready.append(candidate)
                ready.sort()
    if len(order) != len(node_ids):
        raise fail("P3RT-CONTRACT-3421", "research plan graph must be acyclic", {"plan_id": plan_id})
    return order


def build_research_plan_registry(
    *,
    config: ResearchPlanRegistryConfig,
    operation_registry: CanonicalToolOperationRegistry,
    mode_registry: ResearchModeRegistry,
    taxonomy: ResearchCapabilityTaxonomy,
    view_readiness: Phase2ResearchViewReadinessReport,
) -> tuple[ResearchPlanRegistry, ResearchPlanDependencyMatrix, ResearchPlanReadinessReport]:
    del taxonomy
    operations = {(item.tool_id, item.operation_id): item for item in operation_registry.operations}
    modes = {(item.tool_id, item.operation_id, item.mode_id): item for item in mode_registry.modes}
    readiness_by_operation: dict[str, list[ViewReadiness]] = defaultdict(list)
    for item in view_readiness.records:
        readiness_by_operation[item.operation_ref].append(item.status)

    plan_ids: set[str] = set()
    plans: list[ResearchPlanTemplate] = []
    dependencies: list[ResearchPlanDependencyRecord] = []
    readiness_records: list[ResearchPlanReadinessRecord] = []
    ready_plans: list[str] = []
    degraded_plans: list[str] = []
    blocked_plans: list[str] = []

    for plan in sorted(config.plans, key=lambda item: item.plan_id):
        if plan.plan_id in plan_ids:
            raise fail("P3RT-CONTRACT-3422", "duplicate research plan ID", {"plan_id": plan.plan_id})
        plan_ids.add(plan.plan_id)
        node_ids = [item.node_id for item in plan.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise fail("P3RT-CONTRACT-3423", "duplicate node ID in research plan", {"plan_id": plan.plan_id})
        visible_cost = sum(item.visible_call_cost for item in plan.nodes)
        if visible_cost > plan.maximum_visible_calls_per_cycle or visible_cost > 5:
            raise fail("P3RT-BUDGET-3424", "research plan exceeds visible call budget", {"plan_id": plan.plan_id, "visible_call_cost": visible_cost})
        predecessor_map = {item.node_id: item.predecessors for item in plan.nodes}
        order = _topological_order(plan.plan_id, set(node_ids), predecessor_map)
        order_index = {node_id: index for index, node_id in enumerate(order)}
        node_models: list[ResearchPlanNode] = []
        plan_statuses: list[ReadinessStatus] = []
        for node in sorted(plan.nodes, key=lambda item: order_index[item.node_id]):
            operation = operations.get((node.tool_id, node.operation_id))
            if operation is None:
                raise fail("P3RT-CONTRACT-3425", "plan references unknown operation", {"plan_id": plan.plan_id, "node_id": node.node_id})
            if (node.tool_id, node.operation_id, node.requested_mode) not in modes:
                raise fail("P3RT-CONTRACT-3426", "plan references unsupported mode", {"plan_id": plan.plan_id, "node_id": node.node_id, "mode_id": node.requested_mode})
            operation_ref = f"{node.tool_id}/{node.operation_id}"
            statuses = readiness_by_operation.get(operation_ref, [])
            if not statuses or any(status is ViewReadiness.BLOCKED_UPSTREAM for status in statuses):
                status = ReadinessStatus.BLOCKED if node.required else ReadinessStatus.DEGRADED
                reasons = ("P3RT-UPSTREAM-3427",)
            elif any(status is ViewReadiness.DEGRADED for status in statuses):
                status = ReadinessStatus.DEGRADED
                reasons = ("P3RT-DATA-3428",)
            else:
                status = ReadinessStatus.READY
                reasons = ()
            plan_statuses.append(status)
            node_models.append(ResearchPlanNode(
                node_id=node.node_id, tool_id=node.tool_id, operation_id=node.operation_id,
                requested_mode=node.requested_mode, required=node.required,
                predecessors=tuple(sorted(node.predecessors)), stop_conditions=tuple(node.stop_conditions),
                downgrade_policy=node.downgrade_policy, visible_call_cost=node.visible_call_cost,
                priority=node.priority,
            ))
            dependencies.append(ResearchPlanDependencyRecord(
                plan_id=plan.plan_id, node_id=node.node_id,
                predecessor_ids=tuple(sorted(node.predecessors)), topological_index=order_index[node.node_id],
            ))
            readiness_records.append(ResearchPlanReadinessRecord(
                plan_id=plan.plan_id, node_id=node.node_id, status=status,
                available_mode_id=node.requested_mode if status is not ReadinessStatus.BLOCKED else None,
                missing_view_classes=tuple(operation.required_view_classes) if status is ReadinessStatus.BLOCKED else (),
                reason_codes=reasons,
            ))
        plans.append(ResearchPlanTemplate(
            plan_id=plan.plan_id, title=plan.title, description=plan.description,
            subject_kinds=tuple(plan.subject_kinds), nodes=tuple(node_models),
            continuation_allowed=plan.continuation_allowed,
            maximum_visible_calls_per_cycle=plan.maximum_visible_calls_per_cycle,
        ))
        if any(status is ReadinessStatus.BLOCKED for status in plan_statuses):
            blocked_plans.append(plan.plan_id)
        elif any(status is ReadinessStatus.DEGRADED for status in plan_statuses):
            degraded_plans.append(plan.plan_id)
        else:
            ready_plans.append(plan.plan_id)

    source_inputs = (config, operation_registry, mode_registry, view_readiness)
    registry = finalize(ResearchPlanRegistry, {
        "status": ArtifactStatus.READY,
        "lineage": lineage("P3.S34.M03", config.registry_version, source_inputs),
        "registry_version": config.registry_version,
        "plans": tuple(plans),
    })
    matrix = finalize(ResearchPlanDependencyMatrix, {
        "status": ArtifactStatus.READY,
        "lineage": lineage("P3.S34.M03", config.registry_version, source_inputs),
        "records": tuple(sorted(dependencies, key=lambda item: (item.plan_id, item.topological_index, item.node_id))),
    })
    report_status = ArtifactStatus.DEGRADED if blocked_plans or degraded_plans else ArtifactStatus.READY
    report = finalize(ResearchPlanReadinessReport, {
        "status": report_status,
        "lineage": lineage("P3.S34.M03", config.registry_version, source_inputs),
        "records": tuple(sorted(readiness_records, key=lambda item: (item.plan_id, item.node_id))),
        "ready_plan_ids": tuple(sorted(ready_plans)),
        "degraded_plan_ids": tuple(sorted(degraded_plans)),
        "blocked_plan_ids": tuple(sorted(blocked_plans)),
        "reason_codes": () if report_status is ArtifactStatus.READY else ("P3RT-UPSTREAM-3429",),
    })
    return registry, matrix, report
