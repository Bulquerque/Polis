from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from jsonschema import Draft202012Validator

from .canonical import content_hash
from .errors import AuditError, ErrorCategory, error
from .models import (
    AuditEventType, MCPGatewayPolicy, NormalizedToolResult, ToolCallAuditContract, ToolCallAuditEvent,
)

TERMINAL = {
    AuditEventType.EXECUTION_SUCCEEDED, AuditEventType.EXECUTION_FAILED,
    AuditEventType.EXECUTION_TIMED_OUT, AuditEventType.EXECUTION_CANCELLED,
    AuditEventType.RESULT_REJECTED,
}


class MCPResultNormalizer:
    """Normalize an MCP CallToolResult-shaped object without importing the MCP SDK."""

    def normalize(self, raw: Any, *, output_schema: dict[str, Any] | None = None) -> NormalizedToolResult:
        if hasattr(raw, "model_dump"):
            data = raw.model_dump(by_alias=True, mode="python")
        elif isinstance(raw, dict):
            data = dict(raw)
        else:
            data = {
                "content": getattr(raw, "content", None),
                "structuredContent": getattr(raw, "structuredContent", getattr(raw, "structured_content", None)),
                "isError": getattr(raw, "isError", getattr(raw, "is_error", False)),
                "_meta": getattr(raw, "_meta", {}),
            }
        content = data.get("content")
        if not isinstance(content, list):
            raise AuditError(error("P3_S16_RESULT_CONTENT_INVALID", ErrorCategory.AUDIT, "MCP result content must be a list"))
        structured = data.get("structuredContent", data.get("structured_content"))
        if structured is not None and not isinstance(structured, dict):
            raise AuditError(error("P3_S16_RESULT_STRUCTURED_INVALID", ErrorCategory.AUDIT, "structuredContent must be an object"))
        if output_schema is not None:
            if structured is None:
                raise AuditError(error("P3_S16_RESULT_STRUCTURED_REQUIRED", ErrorCategory.AUDIT, "outputSchema declared but structuredContent absent"))
            errors = list(Draft202012Validator(output_schema).iter_errors(structured))
            if errors:
                raise AuditError(error("P3_S16_RESULT_SCHEMA_INVALID", ErrorCategory.AUDIT, "structuredContent does not conform to outputSchema", first_error=errors[0].message))
        host_meta = data.get("_meta") or {}
        if not isinstance(host_meta, dict):
            raise AuditError(error("P3_S16_RESULT_META_INVALID", ErrorCategory.AUDIT, "_meta must be an object"))
        normalized_items = []
        for item in content:
            if hasattr(item, "model_dump"):
                normalized_items.append(item.model_dump(by_alias=True, mode="python"))
            elif isinstance(item, dict):
                normalized_items.append(dict(item))
            else:
                raise AuditError(error("P3_S16_RESULT_CONTENT_BLOCK_INVALID", ErrorCategory.AUDIT, "content blocks must be objects"))
        normalized_content = tuple(normalized_items)
        payload = {"content": normalized_content, "structured_content": structured, "is_error": bool(data.get("isError", data.get("is_error", False)))}
        return NormalizedToolResult(
            content=normalized_content,
            structured_content=structured,
            is_error=payload["is_error"],
            host_meta=host_meta,
            result_hash=content_hash(payload),
            structured_content_hash=content_hash(structured) if structured is not None else None,
        )


class AuditStreamValidator:
    def __init__(self, contract: ToolCallAuditContract) -> None:
        self._contract = contract
        self._allowed = set(contract.allowed_event_types)
        self._transitions = {x.from_event: set(x.to_events) for x in contract.transitions}

    def validate(self, events: Iterable[ToolCallAuditEvent], *, gateway_policy: MCPGatewayPolicy) -> tuple[ToolCallAuditEvent, ...]:
        ordered = tuple(sorted(events, key=lambda x: x.sequence_number))
        if not ordered:
            raise AuditError(error("P3_S16_AUDIT_EMPTY", ErrorCategory.AUDIT, "audit stream is empty"))
        if self._contract.gateway_policy_hash != gateway_policy.content_hash:
            raise AuditError(error("P3_S16_AUDIT_POLICY_HASH_MISMATCH", ErrorCategory.AUDIT, "audit contract does not match gateway policy"))
        first = ordered[0]
        if first.event_type != AuditEventType.EXECUTION_STARTED:
            raise AuditError(error("P3_S16_AUDIT_START_MISSING", ErrorCategory.AUDIT, "first event must be EXECUTION_STARTED"))
        identity = (first.tool_call_id, first.run_id, first.cycle_id, first.snapshot_id, first.person_id, first.tool_id, first.provider_id, first.request_hash)
        terminal_count = 0
        previous = None
        control_map = {(x.person_id, x.tool_id): x for x in gateway_policy.controls}
        control = control_map.get((first.person_id, first.tool_id))
        if control is None:
            raise AuditError(error("P3_S16_AUDIT_CONTROL_MISSING", ErrorCategory.AUDIT, "audit stream has no matching gateway control"))
        for index, event in enumerate(ordered):
            if event.sequence_number != index:
                raise AuditError(error("P3_S16_AUDIT_SEQUENCE_GAP", ErrorCategory.AUDIT, "sequence numbers must be contiguous"))
            if event.event_type not in self._allowed:
                raise AuditError(error("P3_S16_AUDIT_EVENT_FORBIDDEN", ErrorCategory.AUDIT, "event type is not allowed", event=event.event_type.value))
            current_identity = (event.tool_call_id, event.run_id, event.cycle_id, event.snapshot_id, event.person_id, event.tool_id, event.provider_id, event.request_hash)
            if current_identity != identity:
                raise AuditError(error("P3_S16_AUDIT_LINKAGE_BROKEN", ErrorCategory.AUDIT, "audit events do not share identity"))
            if event.secret_material_detected:
                raise AuditError(error("P3_S16_AUDIT_SECRET_DETECTED", ErrorCategory.SECURITY, "secret material detected in audit event"))
            if previous is not None and event.event_type not in self._transitions.get(previous.event_type, set()):
                raise AuditError(error("P3_S16_AUDIT_TRANSITION_INVALID", ErrorCategory.AUDIT, "invalid audit transition", previous=previous.event_type.value, current=event.event_type.value))
            if previous is not None and event.timestamp < previous.timestamp:
                raise AuditError(error("P3_S16_AUDIT_TIME_REVERSED", ErrorCategory.AUDIT, "audit timestamps are not monotonic"))
            if event.event_type in TERMINAL:
                terminal_count += 1
            if event.event_type == AuditEventType.EXECUTION_SUCCEEDED and control.pit_policy.requires_available_at:
                if event.result_available_at is None:
                    raise AuditError(error("P3_S16_AUDIT_AVAILABLE_AT_MISSING", ErrorCategory.TEMPORAL, "PIT-sensitive result requires result_available_at"))
                if gateway_policy.global_controls["execution_context"] == "BACKTEST" and event.result_available_at > gateway_policy.as_of_time:
                    raise AuditError(error("P3_S16_AUDIT_RESULT_AFTER_AS_OF", ErrorCategory.TEMPORAL, "result was unavailable at backtest as_of_time"))
                if event.source_available_at is not None and event.source_available_at > gateway_policy.as_of_time and gateway_policy.global_controls["execution_context"] == "BACKTEST":
                    raise AuditError(error("P3_S16_AUDIT_SOURCE_AFTER_AS_OF", ErrorCategory.TEMPORAL, "source was unavailable at backtest as_of_time"))
            self._validate_material(event)
            previous = event
        if terminal_count != 1 or ordered[-1].event_type not in TERMINAL:
            raise AuditError(error("P3_S16_AUDIT_TERMINAL_INVALID", ErrorCategory.AUDIT, "exactly one terminal event is required"))
        return ordered

    @staticmethod
    def _validate_material(event: ToolCallAuditEvent) -> None:
        if event.event_type == AuditEventType.EXECUTION_SUCCEEDED:
            if event.is_error is not False or not event.result_hash or event.response_schema_validated is not True:
                raise AuditError(error("P3_S16_AUDIT_FAKE_SUCCESS", ErrorCategory.AUDIT, "success requires non-error validated result material"))
        if event.event_type in {AuditEventType.EXECUTION_FAILED, AuditEventType.EXECUTION_TIMED_OUT, AuditEventType.RESULT_REJECTED}:
            if not event.failure_code or not event.failure_stage:
                raise AuditError(error("P3_S16_AUDIT_FAILURE_MATERIAL_MISSING", ErrorCategory.AUDIT, "failure event requires material failure code and stage"))
        if event.event_type == AuditEventType.ATTEMPT_STARTED and not event.attempt_id:
            raise AuditError(error("P3_S16_AUDIT_ATTEMPT_ID_MISSING", ErrorCategory.AUDIT, "attempt event requires attempt_id"))
