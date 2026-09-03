"""Gateway binding and S21 compatibility preflight for P3.S40."""
from __future__ import annotations

from collections.abc import Iterable

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_models import (
    MCPGatewayPolicy,
    PersonToolEntitlementPanel,
    ProviderAdapterRegistryConfig,
    ValidatedPersonContextBundle,
)

from .models import (
    GatewayBindingManifest,
    GatewayRuntimeReadinessReport,
    HandlerRegistryCompletenessReport,
    HandlerRegistryManifest,
    RegistryStatus,
    S21RuntimeBindingManifest,
    S21RuntimePreflightReport,
    S40Lineage,
    TransportKind,
)


def build_gateway_binding_manifest(
    *,
    registry: HandlerRegistryManifest,
    extension_snapshot_hash: str,
    timeout_seconds: float,
    runtime_object_key: str,
    snapshot_id: str,
    lineage: S40Lineage,
) -> GatewayBindingManifest:
    operation_keys = tuple(
        f"{item.tool_id}/{item.operation_id}"
        for item in sorted(registry.operations, key=lambda item: (item.tool_id, item.operation_id))
        if item.qualification_status.value != "BLOCKED_UPSTREAM"
    )
    transports = tuple(sorted({item.transport for item in registry.operations}, key=lambda item: item.value))
    payload = {
        "provider_id": "internal_research",
        "binding_version": "2.0.0",
        "enabled_transports": transports,
        "operation_keys": operation_keys,
        "timeout_seconds": timeout_seconds,
        "extension_snapshot_hash": extension_snapshot_hash,
        "registry_hash": registry.registry_hash,
        "runtime_object_key": runtime_object_key,
        "snapshot_id": snapshot_id,
        "lineage": lineage,
    }
    return GatewayBindingManifest(**payload, binding_hash=content_hash(payload))


def build_gateway_readiness_report(
    *,
    binding: GatewayBindingManifest,
    completeness: HandlerRegistryCompletenessReport,
    execution_profile: str,
    lineage: S40Lineage,
) -> GatewayRuntimeReadinessReport:
    network = {TransportKind.MCP_OPTIONAL, TransportKind.HTTP_OPTIONAL}
    network_enabled = bool(network.intersection(binding.enabled_transports))
    profile = execution_profile.upper()
    reasons: list[str] = []
    if completeness.status is RegistryStatus.FAILED:
        status = RegistryStatus.FAILED
        reasons.append("P3RT-HANDLER-REGISTRY-INCOMPLETE")
    elif profile != "LIVE" and network_enabled:
        status = RegistryStatus.FAILED
        reasons.append("P3RT-RUNTIME-NETWORK-TRANSPORT-IN-BACKTEST")
    elif completeness.status is RegistryStatus.DEGRADED:
        status = RegistryStatus.DEGRADED
        reasons.append("P3RT-UPSTREAM-BLOCKED-OPERATIONS-PRESENT")
    else:
        status = RegistryStatus.READY
    payload = {
        "status": status,
        "execution_profile": profile,
        "operations_ready": len(binding.operation_keys),
        "operations_blocked": len(completeness.blocked_operations),
        "network_transports_enabled": network_enabled,
        "reason_codes": tuple(reasons),
        "lineage": lineage,
    }
    return GatewayRuntimeReadinessReport(**payload, report_hash=content_hash(payload))


def build_s21_runtime_binding(
    *,
    registry: HandlerRegistryManifest,
    gateway_binding: GatewayBindingManifest,
    entitlements: PersonToolEntitlementPanel,
    contexts: ValidatedPersonContextBundle,
    extension_snapshot_hash: str,
    lineage: S40Lineage,
) -> S21RuntimeBindingManifest:
    versions = tuple(sorted({record.entitlement_version for record in entitlements.records}))
    context_hash = content_hash(contexts.model_dump(mode="json"))
    operation_keys = tuple(
        f"{item.tool_id}/{item.operation_id}"
        for item in sorted(registry.operations, key=lambda item: (item.tool_id, item.operation_id))
        if item.qualification_status.value != "BLOCKED_UPSTREAM"
    )
    payload = {
        "binding_id": f"p3.s40.s21.binding.{content_hash(operation_keys)[:16]}",
        "provider_id": "internal_research",
        "operation_keys": operation_keys,
        "entitlement_versions": versions,
        "context_bundle_hash": context_hash,
        "extension_snapshot_hash": extension_snapshot_hash,
        "registry_hash": registry.registry_hash,
        "gateway_binding_hash": gateway_binding.binding_hash,
        "runtime_object_key": gateway_binding.runtime_object_key,
        "lineage": lineage,
    }
    return S21RuntimeBindingManifest(**payload, binding_hash=content_hash(payload))


def build_s21_preflight_report(
    *,
    registry: HandlerRegistryManifest,
    provider_registry: ProviderAdapterRegistryConfig,
    gateway_policy: MCPGatewayPolicy,
    entitlements: PersonToolEntitlementPanel,
    contexts: ValidatedPersonContextBundle,
    execution_profile: str,
    lineage: S40Lineage,
    registry_gateway_mismatches: Iterable[str] = (),
    upstream_reason_codes: Iterable[str] = (),
) -> S21RuntimePreflightReport:
    registry_keys = {(item.tool_id, item.operation_id) for item in registry.operations}
    provider_ids = _enabled_provider_ids(provider_registry)
    entitlement_keys, unknown, missing, person_tools = _inspect_entitlements(
        entitlements, registry_keys, provider_ids
    )
    context_mismatches = _inspect_contexts(contexts, person_tools, gateway_policy)
    network_violations = _network_violations(execution_profile, gateway_policy)
    mismatches = tuple(sorted(set(str(item) for item in registry_gateway_mismatches if str(item))))
    reasons = list(_preflight_reasons(unknown, missing, context_mismatches, network_violations))
    if mismatches:
        reasons.append("P3RT-RUNTIME-REGISTRY-GATEWAY-MISMATCH")
    reasons.extend(str(item) for item in upstream_reason_codes if str(item))
    reason_codes = tuple(dict.fromkeys(reasons))
    payload = {
        "status": RegistryStatus.FAILED if reason_codes else RegistryStatus.READY,
        "operation_count": len(registry_keys),
        "entitlement_operation_count": len(entitlement_keys),
        "unknown_entitlement_operations": tuple(sorted(unknown)),
        "missing_provider_ids": tuple(sorted(missing)),
        "context_tool_mismatches": tuple(sorted(context_mismatches)),
        "network_policy_violations": tuple(sorted(network_violations)),
        "registry_gateway_mismatches": mismatches,
        "reason_codes": reason_codes,
        "lineage": lineage,
    }
    return S21RuntimePreflightReport(**payload, report_hash=content_hash(payload))


def _enabled_provider_ids(registry: ProviderAdapterRegistryConfig) -> set[str]:
    ids = {item.provider_id for item in registry.tool_providers if item.enabled}
    return ids or {item.provider_id for item in registry.providers if item.enabled}


def _inspect_entitlements(entitlements, registry_keys, provider_ids):
    keys: set[tuple[str, str]] = set()
    unknown: list[str] = []
    missing: set[str] = set()
    person_tools: dict[str, set[str]] = {}
    for record in entitlements.records:
        person_tools.setdefault(record.person_id, set()).add(record.tool_id)
        if record.provider_id not in provider_ids:
            missing.add(record.provider_id)
        for operation in record.operations:
            key = (record.tool_id, operation.operation_id)
            keys.add(key)
            if key not in registry_keys:
                unknown.append(f"{record.person_id}:{record.tool_id}/{operation.operation_id}")
    return keys, unknown, missing, person_tools


def _inspect_contexts(contexts, person_tools, policy):
    mismatches: list[str] = []
    for item in contexts.items:
        unexpected = set(item.allowed_tool_ids) - person_tools.get(item.person_id, set())
        if unexpected:
            mismatches.append(f"{item.person_id}:{','.join(sorted(unexpected))}")
        if item.tool_budget > policy.hard_limit_calls_per_person_cycle:
            mismatches.append(f"{item.person_id}:TOOL_BUDGET_EXCEEDS_GATEWAY_LIMIT")
    return mismatches


def _network_violations(profile: str, policy: MCPGatewayPolicy) -> list[str]:
    if profile.upper() != "LIVE" and policy.cache_mode == "live":
        return ["LIVE_CACHE_MODE_IN_BACKTEST"]
    return []


def _preflight_reasons(unknown, missing, context_mismatches, network_violations):
    reasons: list[str] = []
    if unknown:
        reasons.append("P3RT-CONTRACT-UNKNOWN-ENTITLEMENT-OPERATION")
    if missing:
        reasons.append("P3RT-CONFIG-TOOL-PROVIDER-MISSING")
    if context_mismatches:
        reasons.append("P3RT-CONTRACT-CONTEXT-ENTITLEMENT-MISMATCH")
    if network_violations:
        reasons.append("P3RT-RUNTIME-NETWORK-POLICY-VIOLATION")
    return tuple(reasons)
