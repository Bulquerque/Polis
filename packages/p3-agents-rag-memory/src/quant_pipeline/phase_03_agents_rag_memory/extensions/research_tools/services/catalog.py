"""P3.S32.M01 implementation."""

from __future__ import annotations

from collections import Counter

from ..contracts.artifacts import (
    ArtifactStatus,
    CanonicalResearchToolCatalog,
    CanonicalToolOperationRegistry,
    ToolDefinition,
    ToolOperationSpec,
)
from ..contracts.configs import (
    ProviderTransportBindingsConfig,
    ResearchToolCatalogConfig,
    SchemaBundleManifest,
)
from ..core.errors import fail
from ..core.identifiers import (
    HANDLER_ID_RE,
    OPERATION_ID_RE,
    PROVIDER_ID_RE,
    TOOL_ID_RE,
    require_match,
)
from .artifact_construction import finalize, lineage

_REQUIRED_FORBIDDEN_AUTHORITIES = {
    "backtest",
    "feature_selection",
    "model_selection",
    "portfolio_optimization",
    "signal_generation",
    "trade_execution",
}


def _duplicates(values: list[str]) -> list[str]:
    return sorted(value for value, count in Counter(values).items() if count > 1)



def _canonical_inputs(
    catalog_config: ResearchToolCatalogConfig,
    provider_bindings: ProviderTransportBindingsConfig,
    schema_manifest: SchemaBundleManifest,
) -> tuple[ResearchToolCatalogConfig, ProviderTransportBindingsConfig, SchemaBundleManifest]:
    tools = []
    for tool in sorted(catalog_config.tools, key=lambda item: item.tool_id):
        operations = tuple(
            operation.model_copy(
                update={
                    "supported_mode_ids": tuple(sorted(set(operation.supported_mode_ids))),
                    "required_view_classes": tuple(sorted(set(operation.required_view_classes))),
                    "forbidden_authorities": tuple(sorted(set(operation.forbidden_authorities))),
                }
            )
            for operation in sorted(tool.operations, key=lambda item: item.operation_id)
        )
        tools.append(
            tool.model_copy(
                update={
                    "operations": operations,
                    "forbidden_authorities": tuple(sorted(set(tool.forbidden_authorities))),
                }
            )
        )
    canonical_catalog = catalog_config.model_copy(update={"tools": tuple(tools)})
    canonical_providers = provider_bindings.model_copy(
        update={"providers": tuple(sorted(provider_bindings.providers, key=lambda item: item.provider_id))}
    )
    canonical_schemas = schema_manifest.model_copy(
        update={"entries": tuple(sorted(schema_manifest.entries, key=lambda item: item.schema_id))}
    )
    return canonical_catalog, canonical_providers, canonical_schemas


def build_catalog(
    *,
    catalog_config: ResearchToolCatalogConfig,
    provider_bindings: ProviderTransportBindingsConfig,
    schema_manifest: SchemaBundleManifest,
    contract_version: str,
) -> tuple[CanonicalResearchToolCatalog, CanonicalToolOperationRegistry]:
    catalog_config, provider_bindings, schema_manifest = _canonical_inputs(
        catalog_config, provider_bindings, schema_manifest
    )
    if contract_version != catalog_config.contract_version:
        raise fail(
            "P3RT-CONTRACT-0006",
            "extension contract version differs from catalog configuration",
            {"expected": catalog_config.contract_version, "actual": contract_version},
        )

    provider_ids = {item.provider_id for item in provider_bindings.providers}
    schema_by_id = {item.schema_id: item for item in schema_manifest.entries}
    tool_ids = [tool.tool_id for tool in catalog_config.tools]
    duplicate_tools = _duplicates(tool_ids)
    if duplicate_tools:
        raise fail("P3RT-CONTRACT-0001", "duplicate tool IDs", {"tool_ids": duplicate_tools})

    tool_records: list[ToolDefinition] = []
    operation_records: list[ToolOperationSpec] = []
    operation_keys: list[str] = []

    for tool in sorted(catalog_config.tools, key=lambda item: item.tool_id):
        try:
            require_match(tool.tool_id, TOOL_ID_RE, "tool_id")
            require_match(tool.default_provider_id, PROVIDER_ID_RE, "provider_id")
        except ValueError as exc:
            raise fail("P3RT-CONTRACT-0007", str(exc), {"tool_id": tool.tool_id}) from exc
        if tool.default_provider_id not in provider_ids:
            raise fail(
                "P3RT-CONTRACT-0008",
                "tool references an unknown provider binding",
                {"tool_id": tool.tool_id, "provider_id": tool.default_provider_id},
            )
        if not _REQUIRED_FORBIDDEN_AUTHORITIES.issubset(set(tool.forbidden_authorities)):
            raise fail(
                "P3RT-CONTRACT-0004",
                "tool does not declare every forbidden downstream authority",
                {"tool_id": tool.tool_id},
            )

        operation_ids: list[str] = []
        for operation in sorted(tool.operations, key=lambda item: item.operation_id):
            key = f"{tool.tool_id}/{operation.operation_id}"
            operation_keys.append(key)
            operation_ids.append(operation.operation_id)
            try:
                require_match(operation.operation_id, OPERATION_ID_RE, "operation_id")
                require_match(operation.handler_id, HANDLER_ID_RE, "handler_id")
            except ValueError as exc:
                reason = "P3RT-CONTRACT-0005" if "handler" in str(exc) else "P3RT-CONTRACT-0007"
                raise fail(reason, str(exc), {"operation": key}) from exc
            if not operation.supported_mode_ids:
                raise fail("P3RT-MODE-0005", "operation has no supported mode", {"operation": key})
            request_schema = schema_by_id.get(operation.request_schema_ref)
            result_schema = schema_by_id.get(operation.result_schema_ref)
            if request_schema is None or result_schema is None:
                missing = [
                    schema_id
                    for schema_id, value in (
                        (operation.request_schema_ref, request_schema),
                        (operation.result_schema_ref, result_schema),
                    )
                    if value is None
                ]
                raise fail(
                    "P3RT-CONTRACT-0003",
                    "operation references missing schemas",
                    {"operation": key, "schema_ids": missing},
                )
            if not _REQUIRED_FORBIDDEN_AUTHORITIES.issubset(set(operation.forbidden_authorities)):
                raise fail(
                    "P3RT-CONTRACT-0004",
                    "operation does not explicitly declare every forbidden downstream authority",
                    {"operation": key},
                )
            forbidden = tuple(sorted(set(tool.forbidden_authorities) | set(operation.forbidden_authorities)))
            if not _REQUIRED_FORBIDDEN_AUTHORITIES.issubset(set(forbidden)):
                raise fail(
                    "P3RT-CONTRACT-0004",
                    "operation does not preserve forbidden downstream authorities",
                    {"operation": key},
                )
            operation_records.append(
                ToolOperationSpec(
                    tool_id=tool.tool_id,
                    operation_id=operation.operation_id,
                    operation_version=operation.operation_version,
                    description=operation.description,
                    request_schema_ref=request_schema.schema_id,
                    request_schema_hash=request_schema.sha256,
                    result_schema_ref=result_schema.schema_id,
                    result_schema_hash=result_schema.sha256,
                    supported_mode_ids=tuple(sorted(operation.supported_mode_ids)),
                    required_view_classes=tuple(sorted(operation.required_view_classes)),
                    handler_id=operation.handler_id,
                    default_provider_id=tool.default_provider_id,
                    default_transport=operation.default_transport,
                    deterministic_or_seeded=operation.deterministic_or_seeded,
                    max_result_records=operation.max_result_records,
                    forbidden_authorities=forbidden,
                )
            )
        duplicate_operations = _duplicates(operation_ids)
        if duplicate_operations:
            raise fail(
                "P3RT-CONTRACT-0002",
                "duplicate operation IDs inside tool",
                {"tool_id": tool.tool_id, "operation_ids": duplicate_operations},
            )
        tool_records.append(
            ToolDefinition(
                tool_id=tool.tool_id,
                tool_version=tool.tool_version,
                title=tool.title,
                description=tool.description,
                capability_family=tool.capability_family,
                default_provider_id=tool.default_provider_id,
                default_transport=tool.default_transport,
                operation_ids=tuple(sorted(operation_ids)),
                forbidden_authorities=tuple(sorted(tool.forbidden_authorities)),
            )
        )

    duplicate_keys = _duplicates(operation_keys)
    if duplicate_keys:
        raise fail("P3RT-CONTRACT-0002", "duplicate operation keys", {"operations": duplicate_keys})
    if len(tool_records) != catalog_config.expected_tool_count:
        raise fail(
            "P3RT-CONTRACT-0011",
            "tool count differs from contract freeze",
            {"expected": catalog_config.expected_tool_count, "actual": len(tool_records)},
        )
    if len(operation_records) != catalog_config.expected_operation_count:
        raise fail(
            "P3RT-CONTRACT-0012",
            "operation count differs from contract freeze",
            {"expected": catalog_config.expected_operation_count, "actual": len(operation_records)},
        )

    source_inputs = (catalog_config, provider_bindings, schema_manifest)
    catalog = finalize(
        CanonicalResearchToolCatalog,
        {
            "status": ArtifactStatus.READY,
            "lineage": lineage("P3.S32.M01", contract_version, source_inputs),
            "contract_version": contract_version,
            "tools": tuple(tool_records),
            "tool_count": len(tool_records),
        },
    )
    registry = finalize(
        CanonicalToolOperationRegistry,
        {
            "status": ArtifactStatus.READY,
            "lineage": lineage("P3.S32.M01", contract_version, source_inputs),
            "contract_version": contract_version,
            "operations": tuple(sorted(operation_records, key=lambda item: (item.tool_id, item.operation_id))),
            "operation_count": len(operation_records),
        },
    )
    return catalog, registry
