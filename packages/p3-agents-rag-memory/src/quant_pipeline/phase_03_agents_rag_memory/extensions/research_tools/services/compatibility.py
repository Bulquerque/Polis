"""P3.S32.M03 implementation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..contracts.artifacts import (
    AliasRecord,
    ArtifactStatus,
    CanonicalResearchToolCatalog,
    CanonicalToolOperationRegistry,
    CompatibilityAliasRegistry,
    CompatibilityIssue,
    CompatibilitySeverity,
    ExtendedToolRecord,
    ExtendedToolRegistryOverlay,
    LegacyContractProjectionReport,
    ProviderAvailability,
    ProviderTransportOverlay,
    ProviderTransportRecord,
    TransportKind,
)
from ..contracts.configs import CompatibilityAliasConfig
from ..core.errors import fail
from ..core.hashing import content_hash
from .artifact_construction import as_mapping, finalize, lineage

_SECRET_KEYS = {
    "access_token",
    "api_key",
    "authorization",
    "password",
    "refresh_token",
    "secret",
}


def _contains_secret_material(value: object, path: tuple[str, ...] = ()) -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key).casefold()
            next_path = (*path, str(key))
            if key_text in _SECRET_KEYS and item is not None and item != "" and item is not False:
                found.append(".".join(next_path))
            found.extend(_contains_secret_material(item, next_path))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            found.extend(_contains_secret_material(item, (*path, str(index))))
    return found


def _records(value: Mapping[str, Any], *keys: str) -> list[Mapping[str, Any]]:
    for key in keys:
        candidate = value.get(key)
        if isinstance(candidate, (list, tuple)):
            return [item for item in candidate if isinstance(item, Mapping)]
    return []


def _global_limit(policy: Mapping[str, Any]) -> int:
    candidates = [
        policy.get("hard_limit_calls_per_person_cycle"),
        policy.get("max_calls_per_person_cycle"),
    ]
    controls = policy.get("global_controls")
    if isinstance(controls, Mapping):
        candidates.extend(
            [
                controls.get("hard_limit_calls_per_person_cycle"),
                controls.get("max_calls_per_person_cycle"),
            ]
        )
    valid = [int(item) for item in candidates if isinstance(item, int) and not isinstance(item, bool)]
    return min(valid or [5])


def _legacy_provider_map(raw: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    providers = _records(raw, "adapters", "tool_providers", "providers")
    return {str(item.get("provider_id")): item for item in providers if item.get("provider_id")}


def _legacy_transport(provider: Mapping[str, Any]) -> TransportKind:
    protocol = str(provider.get("protocol") or "").upper()
    adapter_id = str(provider.get("adapter_id") or "").casefold()
    interface_id = str(provider.get("interface_id") or "").casefold()
    if protocol in {"LOCAL", "FUNCTION", "PYTHON"} or "local_function" in adapter_id:
        return TransportKind.LOCAL_FUNCTION
    if protocol in {"HTTP", "HTTPS", "REST"} or "http" in adapter_id and "mcp" not in adapter_id:
        return TransportKind.HTTP_OPTIONAL
    if "mcp" in protocol.casefold() or "mcp" in adapter_id or "mcp" in interface_id:
        return TransportKind.MCP_OPTIONAL
    return TransportKind.LOCAL_FUNCTION


def _provider_record(
    *,
    provider_id: str,
    transport: TransportKind,
    legacy: Mapping[str, Any] | None,
) -> ProviderTransportRecord:
    if transport in {
        TransportKind.LOCAL_FUNCTION,
        TransportKind.ARTIFACT_QUERY,
        TransportKind.COMPOSITE_INTERNAL,
    }:
        availability = ProviderAvailability.QUALIFIED_LOCAL
        protocol = "LOCAL"
        protocol_version = "p3-research-local-v1"
        configured = True
        qualified = True
        reasons: tuple[str, ...] = ()
    else:
        availability = ProviderAvailability.OPTIONAL_NOT_CONFIGURED
        protocol = "MCP" if transport == TransportKind.MCP_OPTIONAL else "HTTP"
        protocol_version = str((legacy or {}).get("protocol_version") or "optional")
        configured = False
        qualified = False
        reasons = ("P3RT-PROVIDER-0001",)
    payload = {
        "provider_id": provider_id,
        "transport": transport,
        "availability": availability,
        "protocol": protocol,
        "protocol_version": protocol_version,
        "configured": configured,
        "qualified": qualified,
        "reason_codes": reasons,
    }
    return ProviderTransportRecord(fingerprint=content_hash(payload), **payload)


def build_compatibility(
    *,
    legacy_tool_registry: object,
    legacy_gateway_policy: object,
    legacy_provider_registry: object,
    catalog: CanonicalResearchToolCatalog,
    operation_registry: CanonicalToolOperationRegistry,
    alias_config: CompatibilityAliasConfig,
) -> tuple[
    ExtendedToolRegistryOverlay,
    ProviderTransportOverlay,
    CompatibilityAliasRegistry,
    LegacyContractProjectionReport,
]:
    legacy_tools_raw = as_mapping(legacy_tool_registry, "legacy_tool_registry")
    gateway_raw = as_mapping(legacy_gateway_policy, "legacy_gateway_policy")
    providers_raw = as_mapping(legacy_provider_registry, "legacy_provider_registry")
    secret_paths = sorted(
        set(
            _contains_secret_material(legacy_tools_raw)
            + _contains_secret_material(gateway_raw)
            + _contains_secret_material(providers_raw)
        )
    )
    if secret_paths:
        raise fail(
            "P3RT-CONTRACT-0014",
            "legacy inputs contain secret material rather than credential handles",
            {"paths": secret_paths},
        )

    operation_keys = {(item.tool_id, item.operation_id) for item in operation_registry.operations}
    aliases: list[AliasRecord] = []
    seen_aliases: set[str] = set()
    for item in sorted(alias_config.aliases, key=lambda value: value.alias_tool_id):
        if item.alias_tool_id in seen_aliases:
            raise fail(
                "P3RT-ALIAS-0002",
                "alias is declared more than once",
                {"alias_tool_id": item.alias_tool_id},
            )
        seen_aliases.add(item.alias_tool_id)
        if (item.target_tool_id, item.target_operation_id) not in operation_keys:
            raise fail(
                "P3RT-ALIAS-0001",
                "alias target does not exist",
                {
                    "alias_tool_id": item.alias_tool_id,
                    "target_tool_id": item.target_tool_id,
                    "target_operation_id": item.target_operation_id,
                },
            )
        aliases.append(
            AliasRecord(
                alias_tool_id=item.alias_tool_id,
                target_tool_id=item.target_tool_id,
                target_operation_id=item.target_operation_id,
                fixed_arguments=item.fixed_arguments,
                argument_renames=item.argument_renames,
            )
        )

    legacy_provider_by_id = _legacy_provider_map(providers_raw)
    provider_transports: dict[str, TransportKind] = {
        tool.default_provider_id: tool.default_transport for tool in catalog.tools
    }
    for provider_id, legacy_provider in legacy_provider_by_id.items():
        provider_transports.setdefault(provider_id, _legacy_transport(legacy_provider))
    provider_records = tuple(
        sorted(
            (
                _provider_record(
                    provider_id=provider_id,
                    transport=transport,
                    legacy=legacy_provider_by_id.get(provider_id),
                )
                for provider_id, transport in provider_transports.items()
            ),
            key=lambda item: item.provider_id,
        )
    )
    provider_by_id = {item.provider_id: item for item in provider_records}

    tool_records: list[ExtendedToolRecord] = []
    for tool in catalog.tools:
        provider = provider_by_id[tool.default_provider_id]
        tool_records.append(
            ExtendedToolRecord(
                tool_id=tool.tool_id,
                canonical=True,
                source="EXTENSION",
                provider_id=provider.provider_id,
                transport=provider.transport,
                availability=provider.availability,
                operation_ids=tool.operation_ids,
                reason_codes=provider.reason_codes,
            )
        )
    tool_by_id = {item.tool_id: item for item in catalog.tools}
    for alias in aliases:
        target = tool_by_id[alias.target_tool_id]
        provider = provider_by_id[target.default_provider_id]
        tool_records.append(
            ExtendedToolRecord(
                tool_id=alias.alias_tool_id,
                canonical=False,
                source="LEGACY_ALIAS",
                provider_id=provider.provider_id,
                transport=provider.transport,
                availability=provider.availability,
                operation_ids=(alias.target_operation_id,),
                reason_codes=("P3RT-ALIAS-RESOLVED", *provider.reason_codes),
            )
        )

    issues: list[CompatibilityIssue] = [
        CompatibilityIssue(
            issue_id="legacy-operation-semantics",
            severity=CompatibilitySeverity.WARNING,
            component="P3.S15",
            summary="Legacy allowed_operations may contain administrative actions and is not authoritative.",
            reason_code="P3RT-CONTRACT-0010",
            details={"replacement_authority": "canonical_tool_operation_registry"},
        )
    ]
    external_downgrades = 0
    for provider in provider_records:
        if provider.availability == ProviderAvailability.OPTIONAL_NOT_CONFIGURED:
            external_downgrades += 1
            issues.append(
                CompatibilityIssue(
                    issue_id=f"provider-{provider.provider_id}-optional",
                    severity=CompatibilitySeverity.INFO,
                    component=provider.provider_id,
                    summary="External provider remains optional and is not presented as connected.",
                    reason_code="P3RT-PROVIDER-0001",
                    details={"transport": provider.transport},
                )
            )

    legacy_tool_count = len(_records(legacy_tools_raw, "tools", "records"))
    source_inputs = (
        legacy_tool_registry,
        legacy_gateway_policy,
        legacy_provider_registry,
        catalog,
        operation_registry,
        alias_config,
    )
    version = catalog.contract_version
    overlay = finalize(
        ExtendedToolRegistryOverlay,
        {
            "status": ArtifactStatus.READY,
            "lineage": lineage("P3.S32.M03", version, source_inputs),
            "tools": tuple(sorted(tool_records, key=lambda item: item.tool_id)),
        },
    )
    provider_overlay = finalize(
        ProviderTransportOverlay,
        {
            "status": ArtifactStatus.READY,
            "lineage": lineage("P3.S32.M03", version, source_inputs),
            "providers": provider_records,
            "global_visible_call_limit": _global_limit(gateway_raw),
        },
    )
    alias_registry = finalize(
        CompatibilityAliasRegistry,
        {
            "status": ArtifactStatus.READY,
            "lineage": lineage("P3.S32.M03", version, source_inputs),
            "aliases": tuple(aliases),
        },
    )
    report_status = ArtifactStatus.DEGRADED if issues else ArtifactStatus.READY
    report = finalize(
        LegacyContractProjectionReport,
        {
            "status": report_status,
            "lineage": lineage("P3.S32.M03", version, source_inputs),
            "reason_codes": tuple(sorted({item.reason_code for item in issues})),
            "issues": tuple(issues),
            "legacy_tool_count": legacy_tool_count,
            "aliases_resolved": len(aliases),
            "external_providers_downgraded": external_downgrades,
        },
    )
    return overlay, provider_overlay, alias_registry, report
