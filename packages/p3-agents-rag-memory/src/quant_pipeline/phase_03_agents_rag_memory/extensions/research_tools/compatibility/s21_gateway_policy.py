"""Anti-corruption adapter from the canonical S16 gateway policy to S21.

P3.S16 owns the v2 ``MCPGatewayPolicy`` artifact.  S21 intentionally keeps its
smaller v1 runtime policy model.  This module is the only projection point;
the v2 artifact is never silently treated as an S21 object.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_models import (
    MCPGatewayPolicy as S21MCPGatewayPolicy,
)


def _raw(value: object) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="python")
    elif isinstance(value, Mapping):
        dumped = dict(value)
    else:
        raise TypeError("mcp_gateway_policy must be a mapping or Pydantic model")
    if not isinstance(dumped, dict):
        raise TypeError("mcp_gateway_policy model_dump must return a mapping")
    return dumped


def project_gateway_policy(value: object) -> S21MCPGatewayPolicy:
    """Project S16 v2 or accept an already-native S21 v1 policy.

    The projection is bounded and fail-closed: only explicitly supported
    controls cross the boundary, and unknown execution contexts are rejected.
    """
    if isinstance(value, S21MCPGatewayPolicy):
        return value
    raw = _raw(value)
    if raw.get("schema_id") == "mcp_gateway_policy.v2":
        source_version = raw.get("schema_version")
        if source_version != "2.0.0":
            raise ValueError(f"unsupported S16 gateway policy version: {source_version!r}")
    elif raw.get("schema_version") not in {None, "p3.s21.v1"}:
        raise ValueError(f"unsupported gateway policy source: {raw.get('schema_version')!r}")

    controls = raw.get("global_controls", {})
    if not isinstance(controls, Mapping):
        controls = {}
    execution_context = str(controls.get("execution_context", "BACKTEST")).upper()
    cache_mode = {
        "BACKTEST": "frozen_in_backtest",
        "REPLAY": "replay_only",
        "LIVE": "live",
        "TEST": "frozen_in_backtest",
    }.get(execution_context)
    if cache_mode is None:
        raise ValueError(f"unsupported gateway execution context: {execution_context}")
    max_calls = min(5, max(0, int(controls.get("max_calls_per_person_cycle", 3))))
    timeout_seconds = min(120.0, max(0.001, float(controls.get("hard_timeout_ms", 30_000)) / 1000.0))
    retry_budget = min(3, max(0, int(controls.get("retry_budget_per_run", 1))))
    policy = S21MCPGatewayPolicy.model_validate(
        {
            "schema_version": "p3.s21.v1",
            "policy_version": str(raw.get("policy_version", "2.0.0")),
            "pit_required": True,
            "audit_required": True,
            "cache_mode": cache_mode,
            "cognition_default_calls_per_person_cycle": max_calls,
            "hard_limit_calls_per_person_cycle": max_calls,
            "credential_policy": "handle_only",
            "timeout_seconds": timeout_seconds,
            "max_retry_attempts": retry_budget,
            "retry_backoff_seconds": 0.1,
            "provider_failure_policy": "material_no_fake_success",
        },
        strict=False,
    )
    return policy


def gateway_policy_projection_receipt(value: object, projected: S21MCPGatewayPolicy) -> dict[str, str]:
    """Return a content-addressed audit receipt for the projection boundary."""
    raw = _raw(value)
    payload = {
        "source_schema_id": str(raw.get("schema_id", "p3.s21.v1")),
        "source_schema_version": str(raw.get("schema_version", "p3.s21.v1")),
        "source_content_hash": content_hash(raw),
        "target_schema_id": "p3.s21.gateway_policy.v1",
        "target_schema_version": "p3.s21.v1",
        "target_content_hash": content_hash(projected.model_dump(mode="json")),
    }
    return {**payload, "receipt_hash": content_hash(payload)}


__all__ = ["gateway_policy_projection_receipt", "project_gateway_policy"]
