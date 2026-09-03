"""Immutable operation registry and completeness gates for P3.S40."""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash

from .models import (
    AliasBinding,
    HandlerRegistryCompletenessReport,
    HandlerRegistryManifest,
    OperationDescriptor,
    QualificationStatus,
    RegistryStatus,
    S40Lineage,
    TransportKind,
)

OperationKey = tuple[str, str]
HandlerCallable = Callable[[BaseModel, object], Awaitable[BaseModel]]
ContextFactory = Callable[[object], object]


@dataclass(frozen=True, slots=True)
class ExecutableOperation:
    """Process-local handler and its public contract."""

    descriptor: OperationDescriptor
    request_model: type[BaseModel]
    result_model: type[BaseModel]
    handler: HandlerCallable
    context_factory: ContextFactory

    @property
    def key(self) -> OperationKey:
        return (self.descriptor.tool_id, self.descriptor.operation_id)


@dataclass(frozen=True, slots=True)
class AliasResolution:
    target_key: OperationKey
    arguments: Mapping[str, object]
    alias_applied: bool


class OperationRegistry:
    """Read-only lookup surface used by the gateway."""

    def __init__(
        self,
        operations: Iterable[ExecutableOperation],
        aliases: Iterable[AliasBinding] = (),
    ) -> None:
        operation_map: dict[OperationKey, ExecutableOperation] = {}
        for operation in operations:
            if operation.key in operation_map:
                raise ValueError(f"duplicate operation: {operation.key}")
            operation_map[operation.key] = operation
        alias_map: dict[OperationKey, AliasBinding] = {}
        for alias in aliases:
            alias_key = (alias.alias_tool_id, alias.alias_operation_id)
            if alias_key in operation_map or alias_key in alias_map:
                raise ValueError(f"duplicate or colliding alias: {alias_key}")
            target = (alias.target_tool_id, alias.target_operation_id)
            if target not in operation_map:
                raise ValueError(f"alias target is not registered: {target}")
            alias_map[alias_key] = alias
        self._operations = MappingProxyType(operation_map)
        self._aliases = MappingProxyType(alias_map)

    @property
    def operations(self) -> tuple[ExecutableOperation, ...]:
        return tuple(self._operations[key] for key in sorted(self._operations))

    @property
    def aliases(self) -> tuple[AliasBinding, ...]:
        return tuple(self._aliases[key] for key in sorted(self._aliases))

    def discoverable_operations(self) -> tuple[OperationDescriptor, ...]:
        """Return callable local operations from the immutable dispatch registry."""
        return tuple(
            operation.descriptor
            for operation in self.operations
            if operation.descriptor.qualification_status is not QualificationStatus.BLOCKED_UPSTREAM
        )

    def resolve(
        self,
        tool_id: str,
        operation_id: str,
        arguments: Mapping[str, object],
    ) -> tuple[ExecutableOperation, AliasResolution]:
        key = (tool_id, operation_id)
        operation = self._operations.get(key)
        if operation is not None:
            return operation, AliasResolution(key, MappingProxyType(dict(arguments)), False)
        alias = self._aliases.get(key)
        if alias is None:
            raise KeyError(f"operation not registered: {key}")
        alias_key = key
        renamed = {
            alias.argument_renames.get(str(key), str(key)): value
            for key, value in arguments.items()
        }
        conflicts = sorted(
            key
            for key, value in alias.fixed_arguments.items()
            if key in renamed and renamed[key] != value
        )
        if conflicts:
            raise ValueError(
                f"alias fixed argument conflict for {alias_key}: {', '.join(conflicts)}"
            )
        merged = dict(renamed)
        merged.update(alias.fixed_arguments)
        target = (alias.target_tool_id, alias.target_operation_id)
        return self._operations[target], AliasResolution(
            target_key=target,
            arguments=MappingProxyType(merged),
            alias_applied=True,
        )


def _value(item: object, name: str, default: object = None) -> object:
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


def descriptor_from_binding(
    binding: object,
    *,
    tool_id: str,
    bundle_id: str,
    qualification_status: QualificationStatus,
    provider_id: str = "internal_research",
    transport: TransportKind = TransportKind.COMPOSITE_INTERNAL,
) -> OperationDescriptor:
    modes = tuple(str(getattr(mode, "value", mode)) for mode in _value(binding, "supported_modes", ()))
    return OperationDescriptor(
        tool_id=tool_id,
        operation_id=str(_value(binding, "operation_id")),
        handler_id=str(_value(binding, "handler_id")),
        handler_version=str(_value(binding, "handler_version")),
        provider_id=provider_id,
        transport=transport,
        request_schema_ref=str(_value(binding, "request_schema_ref")),
        result_schema_ref=str(_value(binding, "result_schema_ref")),
        supported_modes=modes,
        required_view_ids=tuple(str(item) for item in _value(binding, "required_view_ids", ())),
        qualification_status=qualification_status,
        deterministic_or_seeded=bool(_value(binding, "deterministic_or_seeded", True)),
        source_bundle_id=bundle_id,
    )


def build_registry_manifest(
    *,
    registry_id: str,
    registry_version: str,
    operations: Iterable[ExecutableOperation],
    aliases: Iterable[AliasBinding],
    lineage: S40Lineage,
) -> HandlerRegistryManifest:
    descriptors = tuple(sorted((item.descriptor for item in operations), key=lambda item: (item.tool_id, item.operation_id)))
    alias_items = tuple(sorted(aliases, key=lambda item: (item.alias_tool_id, item.alias_operation_id)))
    payload = {
        "registry_id": registry_id,
        "registry_version": registry_version,
        "operations": descriptors,
        "aliases": alias_items,
        "lineage": lineage,
    }
    return HandlerRegistryManifest(**payload, registry_hash=content_hash(payload))


def build_completeness_report(
    *, manifest: HandlerRegistryManifest,
    executable_keys: Iterable[OperationKey],
    expected_keys: Iterable[OperationKey] | None,
    lineage: S40Lineage,
) -> HandlerRegistryCompletenessReport:
    manifest_keys = [(item.tool_id, item.operation_id) for item in manifest.operations]
    executable = set(executable_keys)
    expected = set(expected_keys if expected_keys is not None else manifest_keys)
    duplicates = _duplicates(manifest_keys)
    missing = _missing_operations(manifest, manifest_keys, expected, executable)
    blocked = _blocked_operations(manifest)
    alias_errors = _alias_errors(manifest, set(manifest_keys))
    status, reasons = _completeness_status(duplicates, missing, alias_errors, blocked)
    payload = {
        "status": status,
        "expected_operations": len(expected),
        "registered_operations": len(manifest.operations),
        "executable_operations": len(executable),
        "blocked_operations": blocked,
        "missing_operations": tuple(sorted(set(missing))),
        "duplicate_operations": duplicates,
        "alias_errors": alias_errors,
        "reason_codes": reasons,
        "lineage": lineage,
    }
    return HandlerRegistryCompletenessReport(**payload, report_hash=content_hash(payload))


def _duplicates(keys: list[OperationKey]) -> tuple[str, ...]:
    return tuple(sorted({f"{tool}/{op}" for tool, op in keys if keys.count((tool, op)) > 1}))


def _missing_operations(manifest, manifest_keys, expected, executable):
    missing = [f"{tool}/{op}" for tool, op in expected - set(manifest_keys)]
    non_blocked = {
        (item.tool_id, item.operation_id)
        for item in manifest.operations
        if item.qualification_status is not QualificationStatus.BLOCKED_UPSTREAM
    }
    missing.extend(f"{tool}/{op}" for tool, op in non_blocked - executable)
    return sorted(missing)


def _blocked_operations(manifest) -> tuple[str, ...]:
    return tuple(sorted(
        f"{item.tool_id}/{item.operation_id}"
        for item in manifest.operations
        if item.qualification_status is QualificationStatus.BLOCKED_UPSTREAM
    ))


def _alias_errors(manifest, manifest_keys) -> tuple[str, ...]:
    return tuple(sorted(
        f"{alias.alias_tool_id}/{alias.alias_operation_id}:TARGET_MISSING"
        for alias in manifest.aliases
        if (alias.target_tool_id, alias.target_operation_id) not in manifest_keys
    ))


def _completeness_status(duplicates, missing, alias_errors, blocked):
    if duplicates or missing or alias_errors:
        return RegistryStatus.FAILED, ("P3RT-HANDLER-REGISTRY-INCOMPLETE",)
    if blocked:
        return RegistryStatus.DEGRADED, ("P3RT-UPSTREAM-BLOCKED-OPERATIONS-PRESENT",)
    return RegistryStatus.READY, ()
