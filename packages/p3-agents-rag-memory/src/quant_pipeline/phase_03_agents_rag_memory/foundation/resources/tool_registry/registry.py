from __future__ import annotations

from datetime import datetime
from typing import Iterable

from jsonschema import Draft202012Validator

from .canonical import content_hash
from .errors import (
    ContractError,
    ErrorCategory,
    InvariantError,
    PolicyError,
    SecurityError,
    TemporalError,
    error,
)
from .models import (
    ActiveRetroPolicyPatch,
    AvailabilityStatus,
    ConfigurationStatus,
    ConnectivityStatus,
    DiscoverySnapshot,
    EffectiveTool,
    ExecutionContext,
    ProviderAdapter,
    ProviderAdapterRegistry,
    QualificationStatus,
    ToolConfig,
    ToolRegistryConfig,
)

_SECRET_KEYS = {
    "api_key",
    "apikey",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "password",
    "secret",
    "client_secret",
    "cookie",
}


def _scan_for_secret_material(value: object, path: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).casefold().replace("-", "_")
            if normalized in _SECRET_KEYS:
                findings.append(f"{path}.{key}")
            findings.extend(_scan_for_secret_material(item, f"{path}.{key}"))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            findings.extend(_scan_for_secret_material(item, f"{path}[{index}]"))
    return findings


def validate_json_schema(schema: dict[str, object], *, tool_id: str, field_name: str) -> None:
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:  # jsonschema exposes several concrete schema errors
        raise ContractError(
            error(
                "P3_S15_M01_INVALID_JSON_SCHEMA",
                ErrorCategory.CONTRACT,
                f"{field_name} is not a valid JSON Schema Draft 2020-12",
                tool_id=tool_id,
                field_name=field_name,
                cause=type(exc).__name__,
            )
        ) from exc
    if schema.get("type") != "object":
        raise ContractError(
            error(
                "P3_S15_M01_TOOL_SCHEMA_NOT_OBJECT",
                ErrorCategory.CONTRACT,
                "tool request/response schema must have top-level type object",
                tool_id=tool_id,
                field_name=field_name,
            )
        )


def validate_tool_config(tool: ToolConfig, *, as_of_time: datetime) -> None:
    validate_json_schema(tool.request_schema, tool_id=tool.tool_id, field_name="request_schema")
    if tool.response_schema is not None:
        validate_json_schema(tool.response_schema, tool_id=tool.tool_id, field_name="response_schema")
    secret_paths = _scan_for_secret_material(tool.model_dump(mode="python"))
    if secret_paths:
        raise SecurityError(
            error(
                "P3_S15_M01_SECRET_MATERIAL_FORBIDDEN",
                ErrorCategory.SECURITY,
                "tool configuration contains secret-like material; use credential handles only",
                tool_id=tool.tool_id,
                paths=secret_paths,
            )
        )
    if tool.effective_from and tool.effective_from > as_of_time:
        raise TemporalError(
            error(
                "P3_S15_M01_TOOL_NOT_YET_EFFECTIVE",
                ErrorCategory.TEMPORAL,
                "tool effective_from is after as_of_time",
                tool_id=tool.tool_id,
            )
        )
    if tool.effective_to and tool.effective_to < as_of_time:
        raise TemporalError(
            error(
                "P3_S15_M01_TOOL_EXPIRED",
                ErrorCategory.TEMPORAL,
                "tool effective_to is before as_of_time",
                tool_id=tool.tool_id,
            )
        )


def apply_patch(
    tools: tuple[ToolConfig, ...],
    patch: ActiveRetroPolicyPatch | None,
    *,
    config: ToolRegistryConfig,
) -> tuple[tuple[ToolConfig, ...], tuple[str, ...]]:
    if patch is None:
        return tools, ()
    if patch.promoted_at > config.as_of_time:
        raise TemporalError(
            error(
                "P3_S15_M01_FUTURE_PATCH",
                ErrorCategory.TEMPORAL,
                "retro policy patch was promoted after as_of_time",
                patch_id=patch.patch_id,
            )
        )
    if patch.effective_cycle_id != config.cycle_id:
        raise PolicyError(
            error(
                "P3_S15_M01_PATCH_CYCLE_MISMATCH",
                ErrorCategory.POLICY,
                "retro policy patch effective_cycle_id differs from current cycle",
                patch_id=patch.patch_id,
                expected=config.cycle_id,
                actual=patch.effective_cycle_id,
            )
        )
    target_index = next((i for i, item in enumerate(tools) if item.tool_id == patch.change_target), None)
    if target_index is None:
        raise PolicyError(
            error(
                "P3_S15_M01_PATCH_TARGET_UNKNOWN",
                ErrorCategory.POLICY,
                "retro policy patch targets an unknown tool",
                patch_id=patch.patch_id,
                tool_id=patch.change_target,
            )
        )
    if not patch.changes:
        return tools, ("PATCH_METADATA_ONLY_NO_CHANGE",)

    target = tools[target_index]
    payload = target.model_dump(mode="python")
    for change in patch.changes:
        if change.field == "configuration_status":
            if not isinstance(change.value, str):
                raise PolicyError(error("P3_S15_M01_PATCH_VALUE_INVALID", ErrorCategory.POLICY, "configuration_status patch requires string value", field=change.field))
            payload[change.field] = ConfigurationStatus(change.value)
        elif change.field == "timeout_ms":
            if isinstance(change.value, bool) or not isinstance(change.value, int):
                raise PolicyError(error("P3_S15_M01_PATCH_VALUE_INVALID", ErrorCategory.POLICY, "timeout_ms patch requires integer value", field=change.field))
            timeout_payload = target.timeout_policy.model_dump(mode="python")
            timeout_payload["timeout_ms"] = change.value
            payload["timeout_policy"] = timeout_payload
        elif change.field == "max_calls_per_person_cycle":
            if isinstance(change.value, bool) or not isinstance(change.value, int):
                raise PolicyError(error("P3_S15_M01_PATCH_VALUE_INVALID", ErrorCategory.POLICY, "max_calls_per_person_cycle patch requires integer value", field=change.field))
            payload[change.field] = change.value
        elif change.field == "cacheable":
            if not isinstance(change.value, bool):
                raise PolicyError(error("P3_S15_M01_PATCH_VALUE_INVALID", ErrorCategory.POLICY, "cacheable patch requires boolean value", field=change.field))
            payload[change.field] = change.value
        else:
            raise PolicyError(
                error(
                    "P3_S15_M01_PATCH_FIELD_FORBIDDEN",
                    ErrorCategory.POLICY,
                    "retro policy patch attempts to modify a forbidden field",
                    field=change.field,
                )
            )
    try:
        replaced = ToolConfig.model_validate(payload)
    except Exception as exc:
        raise PolicyError(
            error(
                "P3_S15_M01_PATCH_RESULT_INVALID",
                ErrorCategory.POLICY,
                "retro policy patch produces an invalid tool configuration",
                patch_id=patch.patch_id,
                cause=type(exc).__name__,
            )
        ) from exc
    mutable = list(tools)
    mutable[target_index] = replaced
    return tuple(mutable), ()


def _match_discovered(tool: ToolConfig, snapshot: DiscoverySnapshot | None):
    if snapshot is None:
        return None
    discovery_name = tool.discovery_name or tool.name
    return next((item for item in snapshot.tools if item.name == discovery_name), None)


def build_effective_tool(
    tool: ToolConfig,
    *,
    provider: ProviderAdapter,
    snapshot: DiscoverySnapshot | None,
    execution_context: ExecutionContext,
    as_of_time: datetime,
) -> EffectiveTool:
    validate_tool_config(tool, as_of_time=as_of_time)
    discovered = _match_discovered(tool, snapshot)
    reasons: list[str] = []

    connectivity = provider.connectivity_status
    qualification = provider.qualification_status
    discovery_confirmed = discovered is not None

    if snapshot is not None:
        connectivity = snapshot.connectivity_status
        if snapshot.provider_id != provider.provider_id:
            raise InvariantError(
                error(
                    "P3_S15_M01_DISCOVERY_PROVIDER_MISMATCH",
                    ErrorCategory.INVARIANT,
                    "discovery snapshot provider_id differs from provider registry",
                    expected=provider.provider_id,
                    actual=snapshot.provider_id,
                )
            )
        if discovered is None:
            reasons.append("CONFIGURED_TOOL_NOT_DISCOVERED")
        else:
            if content_hash(discovered.input_schema) != content_hash(tool.request_schema):
                raise ContractError(
                    error(
                        "P3_S15_M01_DISCOVERED_INPUT_SCHEMA_MISMATCH",
                        ErrorCategory.CONTRACT,
                        "MCP-discovered inputSchema differs from the frozen configured schema",
                        tool_id=tool.tool_id,
                    )
                )
            if tool.response_schema is not None and discovered.output_schema is not None:
                if content_hash(discovered.output_schema) != content_hash(tool.response_schema):
                    raise ContractError(
                        error(
                            "P3_S15_M01_DISCOVERED_OUTPUT_SCHEMA_MISMATCH",
                            ErrorCategory.CONTRACT,
                            "MCP-discovered outputSchema differs from the frozen configured schema",
                            tool_id=tool.tool_id,
                        )
                    )

    if tool.configuration_status == ConfigurationStatus.DISABLED:
        availability = AvailabilityStatus.DISABLED
        reasons.append("TOOL_DISABLED_BY_CONFIGURATION")
    elif connectivity != ConnectivityStatus.CONNECTED:
        availability = AvailabilityStatus.UNAVAILABLE_DISCONNECTED
        reasons.append("PROVIDER_NOT_CONNECTED")
    elif qualification != QualificationStatus.QUALIFIED:
        availability = AvailabilityStatus.UNAVAILABLE_UNQUALIFIED
        reasons.append("PROVIDER_NOT_QUALIFIED")
    elif snapshot is not None and not discovery_confirmed:
        availability = AvailabilityStatus.FAILED_VALIDATION
        reasons.append("DISCOVERY_CONFIRMATION_FAILED")
    elif execution_context == ExecutionContext.BACKTEST and not tool.pit_policy.backtest_allowed:
        availability = AvailabilityStatus.UNAVAILABLE_UNQUALIFIED
        reasons.append("TOOL_LIVE_ONLY_IN_BACKTEST")
    else:
        availability = AvailabilityStatus.AVAILABLE_QUALIFIED

    return EffectiveTool(
        tool_id=tool.tool_id,
        tool_version=tool.tool_version,
        name=tool.name,
        title=tool.title,
        description=tool.description,
        provider_id=tool.provider_id,
        interface_id=tool.interface_id,
        adapter_id=tool.adapter_id,
        adapter_version=tool.adapter_version,
        capability_family=tool.capability_family,
        configuration_status=tool.configuration_status,
        connectivity_status=connectivity,
        qualification_status=qualification,
        availability_status=availability,
        execution_mode=tool.execution_mode,
        request_schema=tool.request_schema,
        request_schema_hash=content_hash(tool.request_schema),
        response_schema=tool.response_schema,
        response_schema_hash=content_hash(tool.response_schema) if tool.response_schema else None,
        pit_policy=tool.pit_policy,
        credential_policy=tool.credential_policy,
        credential_handle_type=tool.credential_handle_type,
        retry_policy=tool.retry_policy,
        timeout_policy=tool.timeout_policy,
        rate_limit_policy=tool.rate_limit_policy,
        cost_policy=tool.cost_policy,
        cacheable=tool.cacheable,
        deterministic_or_seeded=tool.deterministic_or_seeded,
        sensitivity_class=tool.sensitivity_class,
        permitted_data_classes=tool.permitted_data_classes,
        max_calls_per_person_cycle=tool.max_calls_per_person_cycle,
        protocol=provider.protocol,
        protocol_version=provider.protocol_version,
        provider_fingerprint=provider.fingerprint,
        discovery_snapshot_fingerprint=snapshot.fingerprint if snapshot else None,
        discovery_observed_at=snapshot.observed_at if snapshot else None,
        discovery_confirmed=discovery_confirmed,
        list_changed_supported=(snapshot.list_changed_supported if snapshot else provider.list_changed_supported),
        effective_from=tool.effective_from,
        effective_to=tool.effective_to,
        reason_codes=tuple(sorted(set(reasons))),
        metadata=tool.metadata,
    )


def ensure_unique_tool_ids(tools: Iterable[ToolConfig]) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for tool in tools:
        if tool.tool_id in seen:
            duplicates.add(tool.tool_id)
        seen.add(tool.tool_id)
    if duplicates:
        raise ContractError(
            error(
                "P3_S15_M01_DUPLICATE_TOOL_ID",
                ErrorCategory.CONTRACT,
                "tool IDs must be unique",
                duplicate_tool_ids=sorted(duplicates),
            )
        )
