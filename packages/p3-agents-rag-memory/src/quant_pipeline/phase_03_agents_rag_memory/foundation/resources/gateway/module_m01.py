from __future__ import annotations

from time import perf_counter

from .canonical import compute_artifact_hash, content_hash
from .errors import ContractError, ErrorCategory, error
from .models import ArtifactStatus, GatewayDecision, MCPGatewayPolicy, PersonToolEntitlementPanel, ProviderAdapterRegistry, ToolGatewayConfig, ToolRegistryArtifact
from .policy import assert_no_secret_material, build_controls, compute_coverage, validate_upstream_hashes
from .ports import EventSinkPort


class MCPToolGatewayPolicyBuilder:
    MODULE_ID = "P3.S16.M01"

    def __init__(self, *, event_sink: EventSinkPort) -> None:
        self._events = event_sink

    def run(self, *, tool_registry: ToolRegistryArtifact, person_tool_entitlement_panel: PersonToolEntitlementPanel,
            tool_gateway_config: ToolGatewayConfig, provider_adapter_registry_config: ProviderAdapterRegistry) -> MCPGatewayPolicy:
        started = perf_counter()
        dims = {"run_id": tool_registry.run_id, "cycle_id": tool_registry.cycle_id, "snapshot_id": tool_registry.snapshot_id,
                "module_id": self.MODULE_ID, "as_of_time": tool_registry.as_of_time.isoformat()}
        self._events.emit("module_started", dims)
        try:
            validate_upstream_hashes(tool_registry, person_tool_entitlement_panel)
            assert_no_secret_material(tool_registry.model_dump(mode="python"), source="tool_registry")
            assert_no_secret_material(provider_adapter_registry_config.model_dump(mode="python"), source="provider_adapter_registry_config")
            identity = (tool_registry.run_id, tool_registry.cycle_id, tool_registry.snapshot_id, tool_registry.as_of_time)
            config_identity = (tool_gateway_config.run_id, tool_gateway_config.cycle_id, tool_gateway_config.snapshot_id, tool_gateway_config.as_of_time)
            if identity != config_identity:
                raise ContractError(error("P3_S16_M01_CONFIG_IDENTITY_MISMATCH", ErrorCategory.CONTRACT, "gateway config does not match S15 identity"))
            self._events.emit("input_contract_validated", dims)
            controls = build_controls(registry=tool_registry, entitlements=person_tool_entitlement_panel,
                                      config=tool_gateway_config, providers=provider_adapter_registry_config)
            coverage = compute_coverage(controls)
            if not controls:
                status, issues = ArtifactStatus.EMPTY, ("NO_TOOL_ENTITLEMENT_PAIRS",)
            elif coverage.allowed_pair_count == len(controls):
                status, issues = ArtifactStatus.READY, ()
            elif coverage.allowed_pair_count:
                status, issues = ArtifactStatus.DEGRADED, ("PARTIAL_GATEWAY_AVAILABILITY",)
            else:
                status, issues = ArtifactStatus.DEGRADED, ("NO_ALLOWED_GATEWAY_CONTROLS",)
            global_controls = {
                "execution_context": tool_gateway_config.execution_context.value,
                "pit_required": True,
                "audit_required": True,
                "provider_failure_policy": tool_gateway_config.provider_failure_policy,
                "max_calls_per_person_cycle": tool_gateway_config.max_calls_per_person_cycle,
                "max_total_calls_per_run": tool_gateway_config.max_total_calls_per_run,
                "max_total_cost_per_run": tool_gateway_config.max_total_cost_per_run,
                "max_concurrency_per_provider": tool_gateway_config.max_concurrency_per_provider,
                "hard_timeout_ms": tool_gateway_config.hard_timeout_ms,
                "retry_budget_per_run": tool_gateway_config.retry.retry_budget_per_run,
                "respect_retry_after": tool_gateway_config.retry.respect_retry_after,
                "credential_policy": "HANDLE_ONLY",
                "tool_annotations_untrusted": True,
                "tool_result_untrusted": True,
                "preserve_meta_for_host_only": True,
                "expose_meta_to_model": False,
                "experimental_task_support": False,
            }
            base = {
                "run_id": tool_registry.run_id, "cycle_id": tool_registry.cycle_id, "snapshot_id": tool_registry.snapshot_id,
                "as_of_time": tool_registry.as_of_time, "lineage_id": f"mcp_gateway_policy:{tool_registry.content_hash}:{person_tool_entitlement_panel.content_hash}",
                "status": status, "tool_registry_hash": tool_registry.content_hash,
                "entitlement_panel_hash": person_tool_entitlement_panel.content_hash,
                "gateway_config_hash": content_hash(tool_gateway_config),
                "provider_registry_hash": content_hash(provider_adapter_registry_config),
                "controls": controls, "coverage": coverage, "global_controls": global_controls, "issues": issues,
            }
            digest = compute_artifact_hash({"artifact_name": "mcp_gateway_policy", "schema_id": "mcp_gateway_policy.v2", "schema_version": "2.0.0",
                                            "grain": ("person_id", "tool_id"), "primary_key": ("person_id", "tool_id"), "policy_version": "2.0.0", **base})
            artifact = MCPGatewayPolicy(artifact_id=f"gateway_{digest[:24]}", content_hash=digest, **base)
            self._events.emit("module_succeeded", {**dims, "duration_ms": round((perf_counter()-started)*1000,3),
                              "input_record_count": len(person_tool_entitlement_panel.records), "output_record_count": len(controls),
                              "warning_count": len(issues), "error_count": 0})
            return artifact
        except Exception:
            self._events.emit("module_failed", {**dims, "duration_ms": round((perf_counter()-started)*1000,3),
                              "input_record_count": len(person_tool_entitlement_panel.records), "output_record_count": 0,
                              "warning_count": 0, "error_count": 1})
            raise
