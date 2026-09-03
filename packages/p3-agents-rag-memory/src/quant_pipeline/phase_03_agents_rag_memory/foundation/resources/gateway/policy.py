from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator

from .canonical import content_hash
from .errors import ContractError, ErrorCategory, PolicyError, SecurityError, TemporalError, error
from .models import (
    ArtifactStatus, ApprovalPolicy, AvailabilityStatus, BackoffPolicy, CacheMode, EffectiveCachePolicy,
    EffectiveCredentialPolicy, EffectiveRetryPolicy, EntitlementDecision, ExecutionContext, ExecutionMode,
    GatewayCoverage, GatewayDecision, GatewayExecutionDecision, GatewayToolControl, MCPGatewayPolicy,
    PersonToolEntitlementPanel, ProviderAdapterRegistry, ToolCallRequestEnvelope, ToolGatewayConfig,
    ToolRegistryArtifact,
)

FORBIDDEN_AUTHORITY_FIELDS = {
    "future_return", "candidate_score", "rank_score", "portfolio_weight", "trade_decision", "buy_sell_signal"
}
SECRET_KEYS = {"api_key", "access_token", "refresh_token", "password", "secret", "authorization", "token"}


def _keys_recursive(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            found.add(str(key).lower())
            found |= _keys_recursive(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            found |= _keys_recursive(item)
    return found


def assert_no_secret_material(value: Any, *, source: str) -> None:
    keys = _keys_recursive(value)
    bad_keys = keys & SECRET_KEYS
    if bad_keys:
        raise SecurityError(error(
            "P3_S16_M01_SECRET_MATERIAL_KEY", ErrorCategory.SECURITY,
            "secret-like fields are forbidden in gateway inputs", source=source, fields=sorted(bad_keys),
        ))
    def walk(item: Any) -> None:
        if isinstance(item, str):
            lowered = item.lower()
            if lowered.startswith("bearer ") or lowered.startswith("sk-") or "api_key=" in lowered or "password=" in lowered:
                raise SecurityError(error(
                    "P3_S16_M01_SECRET_MATERIAL_VALUE", ErrorCategory.SECURITY,
                    "secret-like values are forbidden in gateway inputs", source=source,
                ))
        elif isinstance(item, dict):
            for child in item.values(): walk(child)
        elif isinstance(item, (list, tuple)):
            for child in item: walk(child)
    walk(value)


def validate_upstream_hashes(registry: ToolRegistryArtifact, entitlements: PersonToolEntitlementPanel) -> None:
    from .canonical import compute_artifact_hash
    if compute_artifact_hash(registry) != registry.content_hash:
        raise ContractError(error("P3_S16_M01_TOOL_REGISTRY_HASH_MISMATCH", ErrorCategory.CONTRACT, "tool_registry hash is not recomputable"))
    if compute_artifact_hash(entitlements) != entitlements.content_hash:
        raise ContractError(error("P3_S16_M01_ENTITLEMENT_HASH_MISMATCH", ErrorCategory.CONTRACT, "entitlement panel hash is not recomputable"))
    if entitlements.tool_registry_hash != registry.content_hash:
        raise ContractError(error("P3_S16_M01_UPSTREAM_LINKAGE_MISMATCH", ErrorCategory.CONTRACT, "entitlement panel does not reference supplied tool registry"))
    identity_a = (registry.run_id, registry.cycle_id, registry.snapshot_id, registry.as_of_time)
    identity_b = (entitlements.run_id, entitlements.cycle_id, entitlements.snapshot_id, entitlements.as_of_time)
    if identity_a != identity_b:
        raise ContractError(error("P3_S16_M01_UPSTREAM_IDENTITY_MISMATCH", ErrorCategory.CONTRACT, "S15 artifacts do not share run identity"))


def build_controls(*, registry: ToolRegistryArtifact, entitlements: PersonToolEntitlementPanel,
                   config: ToolGatewayConfig, providers: ProviderAdapterRegistry) -> tuple[GatewayToolControl, ...]:
    tool_map = {tool.tool_id: tool for tool in registry.tools}
    controls: list[GatewayToolControl] = []
    for record in sorted(entitlements.records, key=lambda x: (x.person_id, x.tool_id)):
        tool = tool_map.get(record.tool_id)
        if tool is None:
            raise ContractError(error("P3_S16_M01_UNKNOWN_TOOL", ErrorCategory.CONTRACT, "entitlement references unknown tool", tool_id=record.tool_id))
        provider = providers.find(tool.provider_id, tool.interface_id)
        if provider is None:
            raise ContractError(error("P3_S16_M01_PROVIDER_MISSING", ErrorCategory.PROVIDER, "provider adapter absent", provider_id=tool.provider_id))
        if provider.fingerprint != tool.provider_fingerprint:
            raise ContractError(error("P3_S16_M01_PROVIDER_FINGERPRINT_MISMATCH", ErrorCategory.PROVIDER, "provider fingerprint differs from S15 snapshot", provider_id=tool.provider_id))
        if provider.adapter_id != tool.adapter_id or provider.adapter_version != tool.adapter_version:
            raise ContractError(error("P3_S16_M01_ADAPTER_MISMATCH", ErrorCategory.PROVIDER, "adapter differs from frozen tool registry", tool_id=tool.tool_id))
        reasons = list(record.reason_codes)
        if "tools_call" not in provider.capabilities:
            reasons.append("PROVIDER_TOOLS_CALL_CAPABILITY_MISSING")
        decision = GatewayDecision.ALLOWED
        if "PROVIDER_TOOLS_CALL_CAPABILITY_MISSING" in reasons:
            decision = GatewayDecision.BLOCKED
        if record.decision != EntitlementDecision.ALLOWED or "EXECUTE" not in record.allowed_actions:
            decision = GatewayDecision.DENIED
            reasons.append("ENTITLEMENT_EXECUTE_DENIED")
        if tool.availability_status != AvailabilityStatus.AVAILABLE_QUALIFIED:
            decision = GatewayDecision.BLOCKED
            reasons.append("TOOL_NOT_AVAILABLE_QUALIFIED")
        if tool.protocol_version not in config.accepted_protocol_versions:
            decision = GatewayDecision.BLOCKED
            reasons.append("PROTOCOL_VERSION_NOT_ACCEPTED")
        if config.execution_context == ExecutionContext.BACKTEST and not tool.pit_policy.backtest_allowed:
            decision = GatewayDecision.BLOCKED
            reasons.append("TOOL_LIVE_ONLY_IN_BACKTEST")
        if config.execution_context == ExecutionContext.LIVE and not tool.pit_policy.live_allowed:
            decision = GatewayDecision.BLOCKED
            reasons.append("TOOL_NOT_ALLOWED_LIVE")
        approval_required = False
        if tool.execution_mode == ExecutionMode.STATE_CHANGING:
            if config.approval_policy == ApprovalPolicy.STATE_CHANGING_FORBIDDEN:
                decision = GatewayDecision.BLOCKED
                reasons.append("STATE_CHANGING_FORBIDDEN")
            else:
                approval_required = True
        effective_calls = min(record.budget.max_calls_per_cycle, tool.max_calls_per_person_cycle, config.max_calls_per_person_cycle)
        if effective_calls == 0:
            decision = GatewayDecision.DENIED
            reasons.append("ZERO_CALL_BUDGET")
        timeout = min(record.budget.max_latency_ms or tool.timeout_policy.timeout_ms, tool.timeout_policy.timeout_ms, config.hard_timeout_ms)
        tool_attempts = min(tool.retry_policy.max_attempts, config.retry.max_attempts_per_call)
        automatic_retry = tool.execution_mode == ExecutionMode.READ_ONLY
        idempotency_required = tool.execution_mode == ExecutionMode.STATE_CHANGING
        if not automatic_retry:
            tool_attempts = 1
        backoff = BackoffPolicy.EXPONENTIAL_FULL_JITTER if (
            automatic_retry and tool_attempts > 1 and tool.retry_policy.backoff_policy == "EXPONENTIAL_JITTER"
        ) else BackoffPolicy.NONE
        cacheable = bool(tool.cacheable and tool.execution_mode == ExecutionMode.READ_ONLY)
        require_hit = config.execution_context == ExecutionContext.BACKTEST and config.cache.require_cache_hit_in_backtest
        if require_hit and not cacheable:
            decision = GatewayDecision.BLOCKED
            reasons.append("BACKTEST_REQUIRES_FROZEN_CACHE")
        controls.append(GatewayToolControl(
            person_id=record.person_id,
            tool_id=tool.tool_id,
            gateway_decision=decision,
            reason_codes=tuple(sorted(set(reasons))),
            allowed_operations=record.allowed_operations,
            allowed_data_classes=record.allowed_data_classes,
            execution_mode=tool.execution_mode,
            provider_id=tool.provider_id,
            interface_id=tool.interface_id,
            adapter_id=tool.adapter_id,
            adapter_version=tool.adapter_version,
            protocol=tool.protocol,
            protocol_version=tool.protocol_version,
            provider_fingerprint=tool.provider_fingerprint,
            request_schema=tool.request_schema,
            request_schema_hash=tool.request_schema_hash,
            response_schema=tool.response_schema,
            response_schema_hash=tool.response_schema_hash,
            pit_policy=tool.pit_policy,
            credential_policy=EffectiveCredentialPolicy(policy=tool.credential_policy, handle_type=tool.credential_handle_type),
            timeout_ms=timeout,
            max_calls_per_cycle=effective_calls,
            max_cost_per_cycle=record.budget.max_cost_per_cycle,
            rate_limit_per_minute=tool.rate_limit_policy.max_calls_per_minute,
            retry_policy=EffectiveRetryPolicy(
                max_attempts=tool_attempts,
                retryable_failure_codes=tool.retry_policy.retryable_failure_codes,
                backoff_policy=backoff,
                base_delay_ms=config.retry.base_delay_ms,
                max_delay_ms=config.retry.max_delay_ms,
                automatic_retry_allowed=automatic_retry,
                idempotency_key_required=idempotency_required,
            ),
            cache_policy=EffectiveCachePolicy(
                mode=config.cache.mode,
                cacheable=cacheable,
                require_hit=require_hit,
                cache_key_version=config.cache.cache_key_version,
            ),
            approval_required=approval_required,
        ))
    return tuple(controls)


def compute_coverage(controls: tuple[GatewayToolControl, ...]) -> GatewayCoverage:
    return GatewayCoverage(
        evaluated_pair_count=len(controls),
        allowed_pair_count=sum(x.gateway_decision == GatewayDecision.ALLOWED for x in controls),
        denied_pair_count=sum(x.gateway_decision == GatewayDecision.DENIED for x in controls),
        blocked_pair_count=sum(x.gateway_decision == GatewayDecision.BLOCKED for x in controls),
        state_changing_pair_count=sum(x.execution_mode == ExecutionMode.STATE_CHANGING for x in controls),
        cache_required_pair_count=sum(x.cache_policy.require_hit for x in controls),
    )


class GatewayPolicyEvaluator:
    def __init__(self, policy: MCPGatewayPolicy) -> None:
        self._policy = policy
        self._controls = {(x.person_id, x.tool_id): x for x in policy.controls}

    def evaluate(self, request: ToolCallRequestEnvelope) -> GatewayExecutionDecision:
        reasons: list[str] = []
        identity = (request.run_id, request.cycle_id, request.snapshot_id, request.as_of_time)
        expected = (self._policy.run_id, self._policy.cycle_id, self._policy.snapshot_id, self._policy.as_of_time)
        if identity != expected:
            reasons.append("RUN_IDENTITY_MISMATCH")
        control = self._controls.get((request.person_id, request.tool_id))
        if control is None:
            reasons.append("NO_GATEWAY_CONTROL")
            return self._decision(request, GatewayDecision.DENIED, reasons, None)
        if control.gateway_decision != GatewayDecision.ALLOWED:
            reasons.extend(control.reason_codes)
        keys = _keys_recursive(request.arguments)
        forbidden = keys & (FORBIDDEN_AUTHORITY_FIELDS | SECRET_KEYS)
        if forbidden:
            reasons.append("FORBIDDEN_ARGUMENT_FIELDS:" + ",".join(sorted(forbidden)))
        errors = sorted(Draft202012Validator(control.request_schema).iter_errors(request.arguments), key=lambda e: list(e.path))
        if errors:
            reasons.append("ARGUMENT_SCHEMA_INVALID")
        if control.credential_policy.policy.value == "HANDLE_ONLY":
            if request.credential_handle is None:
                reasons.append("CREDENTIAL_HANDLE_REQUIRED")
            elif request.credential_handle.handle_type != control.credential_policy.handle_type:
                reasons.append("CREDENTIAL_HANDLE_TYPE_MISMATCH")
        elif request.credential_handle is not None:
            reasons.append("UNEXPECTED_CREDENTIAL_HANDLE")
        if control.retry_policy.idempotency_key_required and not request.idempotency_key:
            reasons.append("IDEMPOTENCY_KEY_REQUIRED")
        if control.approval_required and not request.approval_ref:
            reasons.append("APPROVAL_REQUIRED")
        if control.cache_policy.require_hit and not request.cache_key:
            reasons.append("FROZEN_CACHE_KEY_REQUIRED")
        if request.budget_state.person_tool_calls_used >= control.max_calls_per_cycle:
            reasons.append("PERSON_TOOL_CALL_BUDGET_EXCEEDED")
        max_total = int(self._policy.global_controls["max_total_calls_per_run"])
        if request.budget_state.total_calls_used >= max_total:
            reasons.append("RUN_CALL_BUDGET_EXCEEDED")
        if control.max_cost_per_cycle is not None and request.estimated_cost is not None:
            if request.budget_state.person_tool_cost_used + request.estimated_cost > control.max_cost_per_cycle:
                reasons.append("PERSON_TOOL_COST_BUDGET_EXCEEDED")
        max_total_cost = self._policy.global_controls.get("max_total_cost_per_run")
        if max_total_cost is not None and request.estimated_cost is not None:
            if request.budget_state.total_cost_used + request.estimated_cost > float(max_total_cost):
                reasons.append("RUN_COST_BUDGET_EXCEEDED")
        decision = GatewayDecision.ALLOWED if not reasons and control.gateway_decision == GatewayDecision.ALLOWED else GatewayDecision.DENIED
        return self._decision(request, decision, reasons, control)

    def _decision(self, request, decision, reasons, control):
        return GatewayExecutionDecision(
            tool_call_id=request.tool_call_id,
            decision=decision,
            reason_codes=tuple(sorted(set(reasons))),
            control_hash=content_hash(control.model_dump(mode="python") if control else {"missing": True}),
            request_hash=content_hash(request),
            effective_timeout_ms=control.timeout_ms if control and decision == GatewayDecision.ALLOWED else None,
            effective_max_attempts=control.retry_policy.max_attempts if control and decision == GatewayDecision.ALLOWED else None,
            cache_required=bool(control and control.cache_policy.require_hit),
            credential_resolution_required=bool(control and control.credential_policy.policy.value == "HANDLE_ONLY"),
        )


def retry_delays_ms(*, tool_call_id: str, attempts: int, base_delay_ms: int, max_delay_ms: int) -> tuple[int, ...]:
    if attempts <= 1:
        return ()
    rng = random.Random(int(content_hash(tool_call_id)[:16], 16))
    delays = []
    for retry_number in range(1, attempts):
        cap = min(max_delay_ms, base_delay_ms * (2 ** (retry_number - 1)))
        delays.append(rng.randint(0, cap))
    return tuple(delays)
