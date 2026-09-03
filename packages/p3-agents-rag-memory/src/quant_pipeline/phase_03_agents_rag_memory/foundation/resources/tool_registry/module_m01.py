from __future__ import annotations

from time import perf_counter

from .canonical import compute_artifact_hash, content_hash
from .errors import ErrorCategory, ProviderError, TemporalError, error
from .models import (
    ActiveRetroPolicyPatch,
    ArtifactStatus,
    AvailabilityStatus,
    DiscoveryMode,
    DiscoverySnapshot,
    ProviderAdapterRegistry,
    RegistryCoverage,
    ToolRegistryArtifact,
    ToolRegistryConfig,
)
from .ports import EventSinkPort, ToolDiscoveryPort
from .registry import apply_patch, build_effective_tool, ensure_unique_tool_ids, validate_tool_config


class ToolRegistryBuilder:
    MODULE_ID = "P3.S15.M01"

    def __init__(
        self,
        *,
        discovery_adapters: dict[str, ToolDiscoveryPort],
        event_sink: EventSinkPort,
    ) -> None:
        self._discovery_adapters = dict(discovery_adapters)
        self._events = event_sink

    async def run(
        self,
        *,
        config: ToolRegistryConfig,
        provider_registry: ProviderAdapterRegistry,
        active_retro_policy_patch: ActiveRetroPolicyPatch | None = None,
    ) -> ToolRegistryArtifact:
        started = perf_counter()
        dims = {
            "run_id": config.run_id,
            "cycle_id": config.cycle_id,
            "snapshot_id": config.snapshot_id,
            "module_id": self.MODULE_ID,
            "as_of_time": config.as_of_time.isoformat(),
        }
        self._events.emit("module_started", dims)
        try:
            ensure_unique_tool_ids(config.tools)
            for tool in config.tools:
                validate_tool_config(tool, as_of_time=config.as_of_time)
            patched_tools, patch_issues = apply_patch(
                config.tools,
                active_retro_policy_patch,
                config=config,
            )
            for tool in patched_tools:
                validate_tool_config(tool, as_of_time=config.as_of_time)
            self._events.emit("input_contract_validated", dims)

            provider_keys = sorted({(tool.provider_id, tool.interface_id) for tool in patched_tools})
            providers = {}
            snapshots: dict[tuple[str, str], DiscoverySnapshot | None] = {}
            for provider_id, interface_id in provider_keys:
                provider = provider_registry.find(provider_id, interface_id)
                if provider is None:
                    raise ProviderError(
                        error(
                            "P3_S15_M01_UNDECLARED_PROVIDER",
                            ErrorCategory.PROVIDER,
                            "tool provider/interface is absent from provider_adapter_registry_config",
                            provider_id=provider_id,
                            interface_id=interface_id,
                        )
                    )
                key = (provider_id, interface_id)
                providers[key] = provider
                snapshot: DiscoverySnapshot | None = None
                if config.discovery_mode != DiscoveryMode.STATIC_ONLY:
                    adapter = self._discovery_adapters.get(f"{provider_id}:{interface_id}") or self._discovery_adapters.get(provider_id)
                    if adapter is None:
                        raise ProviderError(
                            error(
                                "P3_S15_M01_DISCOVERY_ADAPTER_MISSING",
                                ErrorCategory.PROVIDER,
                                "discovery mode requires a discovery adapter",
                                provider_id=provider_id,
                                interface_id=interface_id,
                            )
                        )
                    snapshot = await adapter.discover(provider)
                    if snapshot.observed_at > config.as_of_time:
                        raise TemporalError(
                            error(
                                "P3_S15_M01_DISCOVERY_AFTER_AS_OF",
                                ErrorCategory.TEMPORAL,
                                "tool discovery snapshot was observed after as_of_time",
                                provider_id=provider_id,
                                observed_at=snapshot.observed_at.isoformat(),
                            )
                        )
                    if snapshot.protocol_version != provider.protocol_version:
                        raise ProviderError(
                            error(
                                "P3_S15_M01_PROTOCOL_VERSION_MISMATCH",
                                ErrorCategory.PROVIDER,
                                "discovery protocol version differs from frozen provider registry",
                                provider_id=provider_id,
                            )
                        )
                snapshots[key] = snapshot

            effective = tuple(
                sorted(
                    (
                        build_effective_tool(
                            tool,
                            provider=providers[(tool.provider_id, tool.interface_id)],
                            snapshot=snapshots[(tool.provider_id, tool.interface_id)],
                            execution_context=config.execution_context,
                            as_of_time=config.as_of_time,
                        )
                        for tool in patched_tools
                    ),
                    key=lambda item: item.tool_id,
                )
            )
            coverage = RegistryCoverage(
                configured_tool_count=len(effective),
                available_qualified_count=sum(
                    item.availability_status == AvailabilityStatus.AVAILABLE_QUALIFIED
                    for item in effective
                ),
                disconnected_count=sum(
                    item.availability_status == AvailabilityStatus.UNAVAILABLE_DISCONNECTED
                    for item in effective
                ),
                unqualified_count=sum(
                    item.availability_status == AvailabilityStatus.UNAVAILABLE_UNQUALIFIED
                    for item in effective
                ),
                disabled_count=sum(item.availability_status == AvailabilityStatus.DISABLED for item in effective),
                failed_validation_count=sum(
                    item.availability_status == AvailabilityStatus.FAILED_VALIDATION for item in effective
                ),
            )
            if not effective:
                status = ArtifactStatus.EMPTY
                issues = ("NO_TOOLS_AVAILABLE", *patch_issues)
            elif coverage.available_qualified_count == len(effective):
                status = ArtifactStatus.READY
                issues = patch_issues
            elif coverage.available_qualified_count > 0:
                status = ArtifactStatus.DEGRADED
                issues = ("PARTIAL_TOOL_AVAILABILITY", *patch_issues)
            else:
                status = ArtifactStatus.DEGRADED
                issues = ("NO_AVAILABLE_QUALIFIED_TOOLS", *patch_issues)
            base = {
                "artifact_name": "tool_registry",
                "schema_id": "tool_registry.v2",
                "schema_version": "2.0.0",
                "run_id": config.run_id,
                "cycle_id": config.cycle_id,
                "snapshot_id": config.snapshot_id,
                "as_of_time": config.as_of_time,
                "lineage_id": f"tool_registry:{config.snapshot_id}",
                "status": status,
                "grain": ("tool_id",),
                "primary_key": ("tool_id",),
                "configuration_hash": content_hash(config),
                "provider_registry_hash": content_hash(provider_registry),
                "applied_patch_id": active_retro_policy_patch.patch_id if active_retro_policy_patch else None,
                "tools": effective,
                "coverage": coverage,
                "issues": tuple(issues),
            }
            digest = compute_artifact_hash(base)
            artifact = ToolRegistryArtifact(
                artifact_id=f"tools_{digest[:24]}",
                content_hash=digest,
                **base,
            )
            self._events.emit(
                "module_succeeded",
                {
                    **dims,
                    "duration_ms": round((perf_counter() - started) * 1000, 3),
                    "input_record_count": len(config.tools),
                    "output_record_count": len(effective),
                    "warning_count": len(artifact.issues),
                    "error_count": 0,
                },
            )
            return artifact
        except Exception:
            self._events.emit(
                "module_failed",
                {
                    **dims,
                    "duration_ms": round((perf_counter() - started) * 1000, 3),
                    "input_record_count": len(config.tools),
                    "output_record_count": 0,
                    "warning_count": 0,
                    "error_count": 1,
                },
            )
            raise
