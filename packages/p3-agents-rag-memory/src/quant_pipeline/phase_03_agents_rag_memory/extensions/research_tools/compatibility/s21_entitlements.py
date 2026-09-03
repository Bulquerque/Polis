"""Pure S34 entitlement projection into the frozen S21 contract."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_hashing import stable_id
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_models import (
    ArtifactStatus as S21ArtifactStatus,
    LineageRecord as S21LineageRecord,
    MCPGatewayPolicy,
    PersonToolEntitlementPanel as S21PersonToolEntitlementPanel,
    PersonToolEntitlementRecord as S21PersonToolEntitlementRecord,
    ToolOperationEntitlement,
)

from ..contracts.artifacts import (
    ArtifactStatus,
    CanonicalToolOperationRegistry,
    ProviderAvailability,
    ProviderTransportOverlay,
    ResearchModeRegistry,
)
from ..contracts.boundary_artifacts import Phase2ResearchViewReadinessReport, ReadinessStatus as ViewStatus
from ..contracts.capability_artifacts import (
    DecisionStatus,
    EntitlementOperationDecision,
    EntitlementResolutionAudit,
    PersonResearchCapabilityPanel,
    PersonResearchResourcePanel,
    ResearchPlanRegistry,
)
from ..contracts.capability_configs import ResearchEntitlementPolicyConfig
from ..contracts.operation_models import OPERATION_MODELS
from ..core.errors import fail
from ..core.hashing import content_hash
from ..core.schema import schema_for
from ..services.artifact_construction import finalize, lineage, python_value


def _mapping(value: object) -> Mapping[str, Any]:
    raw = python_value(value)
    if not isinstance(raw, Mapping):
        raise fail("P3RT-CONTRACT-3430", "legacy entitlement or snapshot input must be a mapping")
    return raw


def _records(value: object) -> list[Mapping[str, Any]]:
    raw = _mapping(value)
    rows = raw.get("records", ())
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return []
    return [row for row in rows if isinstance(row, Mapping)]


def _snapshot_context(snapshot: object) -> tuple[str, str, str, object]:
    raw = _mapping(snapshot)
    run_id = str(raw.get("run_id") or "run-research-tools")
    cycle_id = str(raw.get("cycle_id") or "cycle-research-tools")
    snapshot_id = str(raw.get("snapshot_id") or raw.get("artifact_id") or "snapshot-research-tools")
    as_of = raw.get("as_of") or raw.get("as_of_time") or raw.get("decision_time")
    if as_of is None:
        raise fail("P3RT-PIT-3431", "phase3_run_snapshot must expose as_of or decision_time")
    return run_id, cycle_id, snapshot_id, as_of


def _legacy_deny_index(panel: object) -> set[tuple[str, str]]:
    denied: set[tuple[str, str]] = set()
    for row in _records(panel):
        decision = str(row.get("decision", "")).upper()
        if decision in {"DENY", "DENIED"}:
            denied.add((str(row.get("person_id", "")), str(row.get("tool_id", ""))))
    return denied


def _legacy_budget(panel: object, person_id: str, tool_id: str) -> int | None:
    for row in _records(panel):
        if str(row.get("person_id")) != person_id or str(row.get("tool_id")) != tool_id:
            continue
        for direct_key in ("budget_calls_per_cycle", "max_calls_per_cycle"):
            direct_value = row.get(direct_key)
            if isinstance(direct_value, int) and not isinstance(direct_value, bool):
                return max(0, direct_value)
        budget = row.get("budget", {})
        if isinstance(budget, Mapping):
            value = budget.get("max_calls_per_cycle")
            if isinstance(value, int) and not isinstance(value, bool):
                return max(0, value)
    return None


def _narrow_request_schema(tool_id: str, operation_id: str, allowed_modes: tuple[str, ...]) -> tuple[dict[str, Any], dict[str, Any]]:
    models = OPERATION_MODELS.get((tool_id, operation_id))
    if models is None:
        raise fail("P3RT-CONTRACT-3432", "operation models are not registered", {"tool_id": tool_id, "operation_id": operation_id})
    request_model, result_model = models
    request_schema = deepcopy(schema_for(request_model, f"https://quant-pipeline.local/schema/p3/research-tools/{tool_id}/{operation_id}/request/1.0.0"))
    result_schema = schema_for(result_model, f"https://quant-pipeline.local/schema/p3/research-tools/{tool_id}/{operation_id}/result/1.0.0")
    mode_property = request_schema.get("properties", {}).get("research_mode")
    if isinstance(mode_property, dict):
        mode_property.pop("pattern", None)
        mode_property["enum"] = list(allowed_modes)
    return request_schema, result_schema


def _mode_allowed(
    *,
    person_id: str,
    mode,
    capability_scores: Mapping[tuple[str, str], float],
    resource_scores: Mapping[tuple[str, str], float],
    policy: ResearchEntitlementPolicyConfig,
) -> tuple[bool, tuple[str, ...]]:
    floor = policy.minimum_score_by_band[str(mode.band)]
    reasons: list[str] = []
    for capability_id in (*mode.required_capabilities, *mode.required_methods, *policy.required_access_capability_ids):
        if capability_scores.get((person_id, capability_id), 0.0) < floor:
            reasons.append(f"CAPABILITY_BELOW_FLOOR:{capability_id}")
    for resource_id, required in policy.required_resource_scores_by_band[str(mode.band)].items():
        if resource_scores.get((person_id, resource_id), 0.0) < required:
            reasons.append(f"RESOURCE_BELOW_FLOOR:{resource_id}")
    return not reasons, tuple(reasons)


def build_entitlement_overlay(
    *,
    legacy_entitlement_panel: object,
    capability_panel: PersonResearchCapabilityPanel,
    resource_panel: PersonResearchResourcePanel,
    operation_registry: CanonicalToolOperationRegistry,
    mode_registry: ResearchModeRegistry,
    plan_registry: ResearchPlanRegistry,
    view_readiness: Phase2ResearchViewReadinessReport,
    provider_overlay: ProviderTransportOverlay,
    policy: ResearchEntitlementPolicyConfig,
    gateway_policy: MCPGatewayPolicy,
    phase3_run_snapshot: object,
) -> tuple[S21PersonToolEntitlementPanel, EntitlementResolutionAudit]:
    del plan_registry
    run_id, cycle_id, snapshot_id, _ = _snapshot_context(phase3_run_snapshot)
    capability_scores = {(item.person_id, item.capability_id): item.score for item in capability_panel.records}
    resource_scores = {(item.person_id, item.resource_id): item.normalized_score for item in resource_panel.records}
    person_ids = sorted({item.person_id for item in capability_panel.records})
    providers = {item.provider_id: item for item in provider_overlay.providers}
    modes_by_operation: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for mode in mode_registry.modes:
        modes_by_operation[(mode.tool_id, mode.operation_id)].append(mode)
    readiness_by_operation: dict[str, list[ViewStatus]] = defaultdict(list)
    for item in view_readiness.records:
        readiness_by_operation[item.operation_ref].append(item.status)
    legacy_denies = _legacy_deny_index(legacy_entitlement_panel)

    decisions: list[EntitlementOperationDecision] = []
    entitlements: list[S21PersonToolEntitlementRecord] = []
    operations_by_tool: dict[str, list[Any]] = defaultdict(list)
    for operation in operation_registry.operations:
        operations_by_tool[operation.tool_id].append(operation)

    for person_id in person_ids:
        for tool_id in sorted(operations_by_tool):
            operation_entitlements: list[ToolOperationEntitlement] = []
            provider_id = operations_by_tool[tool_id][0].default_provider_id
            provider = providers.get(provider_id)
            provider_ok = bool(
                provider
                and provider.availability.value in policy.allowed_provider_availability
                and provider.qualified
                and provider.configured
            )
            legacy_deny = policy.preserve_applicable_legacy_denies and (person_id, tool_id) in legacy_denies
            legacy_cap = _legacy_budget(legacy_entitlement_panel, person_id, tool_id)
            budget = min(
                policy.maximum_calls_per_cycle,
                provider_overlay.global_visible_call_limit,
                gateway_policy.cognition_default_calls_per_person_cycle,
                gateway_policy.hard_limit_calls_per_person_cycle,
                legacy_cap if legacy_cap is not None else 5,
            )
            for operation in sorted(operations_by_tool[tool_id], key=lambda item: item.operation_id):
                reasons: list[str] = []
                if legacy_deny:
                    reasons.append("P3RT-AUTH-3433")
                if not provider_ok:
                    reasons.append("P3RT-PROVIDER-3434")
                statuses = readiness_by_operation.get(f"{tool_id}/{operation.operation_id}", [])
                if not statuses or any(status.value in policy.blocked_view_statuses for status in statuses):
                    reasons.append("P3RT-UPSTREAM-3435")
                allowed_modes: list[str] = []
                mode_reasons: list[str] = []
                for mode in sorted(modes_by_operation[(tool_id, operation.operation_id)], key=lambda item: (item.band, item.mode_id)):
                    allowed, denied_reasons = _mode_allowed(
                        person_id=person_id, mode=mode, capability_scores=capability_scores,
                        resource_scores=resource_scores, policy=policy,
                    )
                    if allowed:
                        allowed_modes.append(mode.mode_id)
                    else:
                        mode_reasons.extend(f"{mode.mode_id}:{reason}" for reason in denied_reasons)
                if not allowed_modes:
                    reasons.append("P3RT-AUTH-3436")
                if budget <= 0:
                    reasons.append("P3RT-BUDGET-3437")
                decision = DecisionStatus.DENY if reasons else DecisionStatus.ALLOW
                decisions.append(EntitlementOperationDecision(
                    person_id=person_id, tool_id=tool_id, operation_id=operation.operation_id,
                    decision=decision, allowed_mode_ids=tuple(allowed_modes) if decision is DecisionStatus.ALLOW else (),
                    provider_id=provider_id if provider_ok else None,
                    budget_calls_per_cycle=budget,
                    reason_codes=tuple(reasons + mode_reasons),
                ))
                if decision is DecisionStatus.ALLOW:
                    request_schema, result_schema = _narrow_request_schema(tool_id, operation.operation_id, tuple(allowed_modes))
                    operation_entitlements.append(ToolOperationEntitlement(
                        operation_id=operation.operation_id,
                        arguments_schema=request_schema,
                        result_schema=result_schema,
                        read_only=True,
                        point_in_time_safe=True,
                    ))
            if operation_entitlements:
                entitlements.append(S21PersonToolEntitlementRecord(
                    person_id=person_id,
                    tool_id=tool_id,
                    provider_id=provider_id,
                    credential_handle=None,
                    budget_calls_per_cycle=budget,
                    operations=tuple(operation_entitlements),
                    entitlement_version=policy.policy_version,
                ))

    source_payloads = (
        legacy_entitlement_panel, capability_panel, resource_panel, operation_registry,
        mode_registry, view_readiness, provider_overlay, policy, gateway_policy, phase3_run_snapshot,
    )
    source_ids = tuple(sorted({
        str(_mapping(legacy_entitlement_panel).get("artifact_id") or "legacy-person-tool-entitlement-panel"),
        capability_panel.artifact_id, resource_panel.artifact_id,
        operation_registry.artifact_id, mode_registry.artifact_id,
        view_readiness.artifact_id, provider_overlay.artifact_id,
    }))
    source_hashes = {source_id: content_hash(source_id) for source_id in source_ids}
    s21_lineage = S21LineageRecord(
        lineage_id=stable_id("lin", "P3.S34.M04", source_ids, source_hashes),
        source_artifact_ids=source_ids,
        source_hashes=source_hashes,
        producer_module_id="P3.S34.M04",
    )
    panel_status = S21ArtifactStatus.READY if entitlements else S21ArtifactStatus.EMPTY_VALID
    panel = S21PersonToolEntitlementPanel(
        status=panel_status,
        records=tuple(entitlements),
        lineage=s21_lineage,
        reason_code=None if entitlements else "P3RT-AUTH-3438",
    )
    audit_status = ArtifactStatus.READY if entitlements else ArtifactStatus.DEGRADED
    audit = finalize(EntitlementResolutionAudit, {
        "status": audit_status,
        "lineage": lineage("P3.S34.M04", policy.policy_version, source_payloads),
        "decisions": tuple(sorted(decisions, key=lambda item: (item.person_id, item.tool_id, item.operation_id))),
        "allowed_decision_count": sum(item.decision is DecisionStatus.ALLOW for item in decisions),
        "denied_decision_count": sum(item.decision is DecisionStatus.DENY for item in decisions),
        "reason_codes": () if entitlements else ("P3RT-AUTH-3438",),
    })
    return panel, audit
