"""Single-authority bootstrap orchestration for P3.S40.M01-M03."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_models import (
    PersonToolEntitlementPanel,
    ProviderAdapterRegistryConfig,
    ValidatedPersonContextBundle,
)

from .assembly_support import expected_keys, lineage, parse, registry
from .boundary_runtime import BoundaryRuntimeFactory
from .gateway import CompositeResearchToolGateway, InMemoryTraceSink
from .models import (
    GatewayBindingManifest,
    GatewayRuntimeReadinessReport,
    HandlerRegistryCompletenessReport,
    HandlerRegistryManifest,
    RegistryStatus,
    S21RuntimeBindingManifest,
)
from .object_store import ProcessLocalRuntimeStore, require_runtime_store
from ..compatibility.s21_gateway_policy import project_gateway_policy
from .preflight import (
    build_gateway_binding_manifest,
    build_gateway_readiness_report,
    build_s21_preflight_report,
    build_s21_runtime_binding,
)
from .registry import OperationRegistry, build_completeness_report, build_registry_manifest

_REGISTRY_PREFIX = "p3.s40.operation_registry:"
_GATEWAY_PREFIX = "p3.s40.gateway:"


def _required_ports(inputs: Mapping[str, Any]) -> tuple[str, ...]:
    ports: list[str] = []
    if "corpus_tool_handler_bundle" in inputs:
        ports.append("corpus_repository")
    if "market_tool_handler_bundle" in inputs or "options_tool_handler_bundle" in inputs:
        ports.append("pit_market_query_port")
    if "macro_tool_handler_bundle" in inputs:
        ports.append("pit_macro_query_port")
    if "company_tool_handler_bundle" in inputs:
        ports.append("company_pit_query_port")
    if "quant_tool_handler_bundle" in inputs:
        ports.append("quant_pit_query_port")
    return tuple(dict.fromkeys(ports))


def _with_bootstrap_failures(
    report: HandlerRegistryCompletenessReport,
    *,
    missing_ports: tuple[str, ...],
    family_failures: tuple[str, ...],
) -> HandlerRegistryCompletenessReport:
    if not missing_ports and not family_failures:
        return report
    payload = report.model_dump(mode="python", exclude={"report_hash"})
    payload["status"] = RegistryStatus.FAILED
    payload["missing_operations"] = tuple(sorted({
        *report.missing_operations,
        *(f"runtime_port:{name}" for name in missing_ports),
        *(f"family_gate:{name}" for name in family_failures),
    }))
    reasons = list(report.reason_codes)
    if missing_ports:
        reasons.append("P3RT-RUNTIME-REQUIRED-PORT-MISSING")
    if family_failures:
        reasons.append("P3RT-FAMILY-QUALIFICATION-INVALID")
    payload["reason_codes"] = tuple(dict.fromkeys(reasons))
    return HandlerRegistryCompletenessReport(**payload, report_hash=content_hash(payload))


def _status_failures(inputs: Mapping[str, Any]) -> tuple[str, ...]:
    """Reject explicit family failures while preserving honest degraded/blocked states."""
    artifact_names = (
        "corpus_operation_mode_qualification",
        "corpus_tool_readiness_report",
        "market_derivatives_operation_mode_qualification",
        "market_derivatives_tool_readiness_report",
        "macro_operation_mode_qualification",
        "macro_tool_readiness_report",
        "company_operation_readiness_panel",
        "company_operation_mode_qualification",
        "quant_operation_mode_qualification",
    )
    failures: list[str] = []
    for name in artifact_names:
        value = inputs.get(name)
        for path, status in _iter_statuses(value, name):
            if status in {"FAILED", "FAIL", "ERROR", "INVALID", "INCOMPATIBLE"}:
                failures.append(f"{path}:{status}")
    return tuple(sorted(set(failures)))


def _iter_statuses(value: object, path: str):
    if isinstance(value, Mapping):
        raw = value.get("status")
        if raw is not None:
            status = str(getattr(raw, "value", raw)).upper()
            yield path, status
        records = value.get("records", ())
        if isinstance(records, (tuple, list)):
            for index, record in enumerate(records):
                yield from _iter_statuses(record, f"{path}.records[{index}]")
        return
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        yield from _iter_statuses(dump(mode="python"), path)


def _evidence_link_failures(inputs: Mapping[str, Any]) -> tuple[str, ...]:
    failures: list[str] = []
    for family in ("company", "quant"):
        evidence_name = f"{family}_qualification_evidence_package"
        bundle_name = f"{family}_tool_handler_bundle"
        qualification_name = f"{family}_operation_mode_qualification"
        if not any(name in inputs for name in (evidence_name, bundle_name, qualification_name)):
            continue
        evidence = inputs.get(evidence_name)
        bundle = inputs.get(bundle_name)
        qualification = inputs.get(qualification_name)
        if not all(isinstance(item, Mapping) for item in (evidence, bundle, qualification)):
            failures.append(f"{evidence_name}:INVALID_PAYLOAD")
            continue
        expected_bundle_hash = bundle.get("bundle_hash") or bundle.get("content_hash")
        expected_qualification_hash = qualification.get("matrix_hash") or qualification.get("content_hash")
        if evidence.get("bundle_hash") != expected_bundle_hash:
            failures.append(f"{evidence_name}:BUNDLE_HASH_MISMATCH")
        if evidence.get("qualification_hash") != expected_qualification_hash:
            failures.append(f"{evidence_name}:QUALIFICATION_HASH_MISMATCH")
        declared_hash = evidence.get("content_hash")
        body = dict(evidence)
        body.pop("content_hash", None)
        if not isinstance(declared_hash, str) or declared_hash != content_hash(body):
            failures.append(f"{evidence_name}:CONTENT_HASH_MISMATCH")
    return tuple(sorted(set(failures)))


def _snapshot_id(context: ModuleExecutionContext, inputs: Mapping[str, Any]) -> str:
    explicit = inputs.get("snapshot_id")
    if isinstance(explicit, str) and explicit:
        return explicit
    if context.run_identity is not None:
        return context.run_identity.snapshot_id
    snapshot = inputs.get("research_tool_extension_snapshot")
    if isinstance(snapshot, Mapping):
        for key in ("snapshot_id", "extension_snapshot_id", "artifact_id"):
            value = snapshot.get(key)
            if isinstance(value, str) and value:
                return value
    return str(context.config.get("research_snapshot_id", "extension-snapshot"))


def build_registry_runtime(
    *,
    context: ModuleExecutionContext,
    inputs: Mapping[str, Any],
    module_id: str = "P3.S40.M01",
    persist: bool = False,
    allow_explicit: bool | None = None,
) -> tuple[OperationRegistry, HandlerRegistryManifest, HandlerRegistryCompletenessReport]:
    if "research_data_boundary_bundle" in inputs:
        boundary = BoundaryRuntimeFactory().materialize(
            boundary_payload=inputs["research_data_boundary_bundle"],
            context=context,
            required_ports=_required_ports(inputs),
        )
        effective_services = boundary.services
        missing_ports = boundary.missing_required_ports
    elif allow_explicit:
        # Backward-compatible focused TEST helper; canonical M01 always declares S33.
        effective_services = context.services
        missing_ports = ()
    else:
        raise KeyError("research_data_boundary_bundle")
    operation_registry = registry(
        context,
        inputs,
        services=effective_services,
        allow_explicit=allow_explicit,
    )
    # All declared family policies, snapshots, readiness reports and evidence
    # participate in the authority hash.  No hidden service can silently
    # replace a declared qualification decision.
    source_lineage = lineage(module_id, inputs, tuple(inputs))
    manifest = build_registry_manifest(
        registry_id="p3.s40.internal.handler.registry",
        registry_version="2.0.0",
        operations=operation_registry.operations,
        aliases=operation_registry.aliases,
        lineage=source_lineage,
    )
    report = build_completeness_report(
        manifest=manifest,
        executable_keys=(item.key for item in operation_registry.operations),
        expected_keys=expected_keys(inputs),
        lineage=source_lineage,
    )
    family_failures = tuple(sorted({
        *_status_failures(inputs),
        *_evidence_link_failures(inputs),
    }))
    report = _with_bootstrap_failures(
        report,
        missing_ports=missing_ports,
        family_failures=family_failures,
    )
    if persist:
        store = require_runtime_store(context.services)
        store.put(f"{_REGISTRY_PREFIX}{manifest.registry_hash}", operation_registry)
    return operation_registry, manifest, report


def create_gateway_runtime(*, context: ModuleExecutionContext, inputs: Mapping[str, Any]) -> CompositeResearchToolGateway:
    """Focused TEST helper; the canonical M01->M02 path uses the runtime store."""
    operation_registry, _, _ = build_registry_runtime(
        context=context,
        inputs=inputs,
        allow_explicit=bool(context.config.get("allow_explicit_research_tool_operations", True)),
    )
    return CompositeResearchToolGateway(
        registry=operation_registry,
        snapshot_id=_snapshot_id(context, inputs),
        execution_profile=context.profile.value,
        deterministic_seed=int(context.config.get("deterministic_seed", 0)),
        timeout_seconds=float(context.config.get("tool_timeout_seconds", 30.0)),
        trace_sink=context.services.get("research_tool_trace_sink") or InMemoryTraceSink(),
    )


async def execute_m01(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    _, manifest, report = build_registry_runtime(context=context, inputs=inputs, persist=True)
    return {
        "internal_handler_registry": manifest.model_dump(mode="json"),
        "handler_registry_completeness_report": report.model_dump(mode="json"),
    }


async def execute_m02(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    manifest = parse(HandlerRegistryManifest, inputs["internal_handler_registry"])
    completeness = parse(
        HandlerRegistryCompletenessReport,
        inputs["handler_registry_completeness_report"],
    )
    store = require_runtime_store(context.services)
    registry_key = f"{_REGISTRY_PREFIX}{manifest.registry_hash}"
    operation_registry = store.get(registry_key)
    if not isinstance(operation_registry, OperationRegistry):
        raise TypeError("stored S40 registry has an invalid runtime type")
    actual_keys = tuple(
        f"{item.descriptor.tool_id}/{item.descriptor.operation_id}"
        for item in operation_registry.operations
        if item.descriptor.qualification_status.value != "BLOCKED_UPSTREAM"
    )
    manifest_keys = tuple(
        f"{item.tool_id}/{item.operation_id}"
        for item in manifest.operations
        if item.qualification_status.value != "BLOCKED_UPSTREAM"
    )
    if sorted(actual_keys) != sorted(manifest_keys):
        raise RuntimeError("stored registry does not match M01 manifest")

    gateway = CompositeResearchToolGateway(
        registry=operation_registry,
        snapshot_id=_snapshot_id(context, inputs),
        execution_profile=context.profile.value,
        deterministic_seed=int(context.config.get("deterministic_seed", 0)),
        timeout_seconds=float(context.config.get("tool_timeout_seconds", 30.0)),
        trace_sink=context.services.get("research_tool_trace_sink") or InMemoryTraceSink(),
    )
    source_lineage = lineage(
        "P3.S40.M02",
        inputs,
        ("internal_handler_registry", "handler_registry_completeness_report", "research_tool_extension_snapshot"),
    )
    extension_hash = content_hash(inputs["research_tool_extension_snapshot"])
    snapshot_id = _snapshot_id(context, inputs)
    gateway_key = (
        f"{_GATEWAY_PREFIX}{manifest.registry_hash}:"
        f"{extension_hash}:{snapshot_id}"
    )
    binding = build_gateway_binding_manifest(
        registry=manifest,
        extension_snapshot_hash=extension_hash,
        timeout_seconds=float(context.config.get("tool_timeout_seconds", 30.0)),
        runtime_object_key=gateway_key,
        snapshot_id=snapshot_id,
        lineage=source_lineage,
    )
    store.put(gateway_key, gateway)
    readiness = build_gateway_readiness_report(
        binding=binding,
        completeness=completeness,
        execution_profile=context.profile.value,
        lineage=source_lineage,
    )
    return {
        "composite_tool_gateway_binding_manifest": binding.model_dump(mode="json"),
        "gateway_runtime_readiness_report": readiness.model_dump(mode="json"),
    }


async def execute_m03(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    registry_manifest = parse(HandlerRegistryManifest, inputs["internal_handler_registry"])
    completeness = parse(HandlerRegistryCompletenessReport, inputs["handler_registry_completeness_report"])
    gateway_binding = parse(GatewayBindingManifest, inputs["composite_tool_gateway_binding_manifest"])
    gateway_readiness = parse(GatewayRuntimeReadinessReport, inputs["gateway_runtime_readiness_report"])
    provider = parse(ProviderAdapterRegistryConfig, inputs["provider_adapter_registry_config"])
    policy = project_gateway_policy(inputs["mcp_gateway_policy"])
    entitlements = parse(PersonToolEntitlementPanel, inputs["extended_person_tool_entitlement_panel"])
    contexts = parse(ValidatedPersonContextBundle, inputs["extended_validated_person_context_bundle"])
    store = require_runtime_store(context.services)

    mismatches: list[str] = []
    if gateway_binding.registry_hash != registry_manifest.registry_hash:
        mismatches.append("REGISTRY_HASH_MISMATCH")
    expected_extension_hash = content_hash(inputs["research_tool_extension_snapshot"])
    if gateway_binding.extension_snapshot_hash != expected_extension_hash:
        mismatches.append("EXTENSION_SNAPSHOT_HASH_MISMATCH")
    try:
        gateway = store.get(gateway_binding.runtime_object_key)
    except KeyError:
        gateway = None
        mismatches.append("GATEWAY_RUNTIME_OBJECT_MISSING")
    if not isinstance(gateway, CompositeResearchToolGateway):
        mismatches.append("GATEWAY_RUNTIME_OBJECT_INVALID")
    manifest_keys = tuple(sorted(
        f"{item.tool_id}/{item.operation_id}"
        for item in registry_manifest.operations
        if item.qualification_status.value != "BLOCKED_UPSTREAM"
    ))
    if tuple(sorted(gateway_binding.operation_keys)) != manifest_keys:
        mismatches.append("GATEWAY_OPERATION_SET_MISMATCH")
    canonical_keys = expected_keys(inputs)
    registered_keys = {
        (item.tool_id, item.operation_id)
        for item in registry_manifest.operations
    }
    if canonical_keys is None or canonical_keys != registered_keys:
        mismatches.append("CANONICAL_OPERATION_REGISTRY_MISMATCH")

    upstream_reasons: list[str] = []
    if completeness.status is RegistryStatus.FAILED:
        upstream_reasons.append("P3RT-HANDLER-REGISTRY-INCOMPLETE")
    if gateway_readiness.status is RegistryStatus.FAILED:
        upstream_reasons.append("P3RT-RUNTIME-GATEWAY-NOT-READY")

    source_lineage = lineage("P3.S40.M03", inputs, tuple(inputs))
    binding = build_s21_runtime_binding(
        registry=registry_manifest,
        gateway_binding=gateway_binding,
        entitlements=entitlements,
        contexts=contexts,
        extension_snapshot_hash=expected_extension_hash,
        lineage=source_lineage,
    )
    report = build_s21_preflight_report(
        registry=registry_manifest,
        provider_registry=provider,
        gateway_policy=policy,
        entitlements=entitlements,
        contexts=contexts,
        execution_profile=context.profile.value,
        lineage=source_lineage,
        registry_gateway_mismatches=mismatches,
        upstream_reason_codes=upstream_reasons,
    )
    return {
        "s21_research_tool_runtime_binding_manifest": binding.model_dump(mode="json"),
        "s21_runtime_preflight_report": report.model_dump(mode="json"),
    }


def resolve_s21_gateway(
    binding_payload: object,
    services: Mapping[str, Any],
) -> CompositeResearchToolGateway:
    """Composition-root resolver used before constructing the real S21 runtime."""
    binding = parse(S21RuntimeBindingManifest, binding_payload)
    gateway = require_runtime_store(services).get(binding.runtime_object_key)
    if not isinstance(gateway, CompositeResearchToolGateway):
        raise TypeError("S21 binding resolved a non-gateway runtime object")
    return gateway
