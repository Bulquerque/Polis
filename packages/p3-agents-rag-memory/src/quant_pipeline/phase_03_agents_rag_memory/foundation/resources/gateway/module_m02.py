from __future__ import annotations

from time import perf_counter

from .canonical import compute_artifact_hash
from .errors import ContractError, ErrorCategory, error
from .models import (
    ArtifactStatus, AuditEventType, AuditFieldRule, AuditTransition, MCPGatewayPolicy, ToolCallAuditContract,
)
from .ports import EventSinkPort


class ToolCallAuditContractBuilder:
    MODULE_ID = "P3.S16.M02"

    def __init__(self, *, event_sink: EventSinkPort) -> None:
        self._events = event_sink

    def run(self, *, mcp_gateway_policy: MCPGatewayPolicy) -> ToolCallAuditContract:
        started = perf_counter()
        dims = {"run_id": mcp_gateway_policy.run_id, "cycle_id": mcp_gateway_policy.cycle_id,
                "snapshot_id": mcp_gateway_policy.snapshot_id, "module_id": self.MODULE_ID,
                "as_of_time": mcp_gateway_policy.as_of_time.isoformat()}
        self._events.emit("module_started", dims)
        try:
            if compute_artifact_hash(mcp_gateway_policy) != mcp_gateway_policy.content_hash:
                raise ContractError(error("P3_S16_M02_POLICY_HASH_MISMATCH", ErrorCategory.CONTRACT, "gateway policy hash is not recomputable"))
            self._events.emit("input_contract_validated", dims)
            allowed = tuple(AuditEventType)
            terminal = (AuditEventType.EXECUTION_SUCCEEDED, AuditEventType.EXECUTION_FAILED,
                        AuditEventType.EXECUTION_TIMED_OUT, AuditEventType.EXECUTION_CANCELLED, AuditEventType.RESULT_REJECTED)
            transitions = (
                AuditTransition(from_event=AuditEventType.EXECUTION_STARTED,
                                to_events=(AuditEventType.ATTEMPT_STARTED, AuditEventType.CACHE_HIT, AuditEventType.EXECUTION_CANCELLED)),
                AuditTransition(from_event=AuditEventType.ATTEMPT_STARTED,
                                to_events=(AuditEventType.ATTEMPT_FAILED, AuditEventType.EXECUTION_SUCCEEDED,
                                           AuditEventType.EXECUTION_FAILED, AuditEventType.EXECUTION_TIMED_OUT,
                                           AuditEventType.RESULT_REJECTED)),
                AuditTransition(from_event=AuditEventType.ATTEMPT_FAILED,
                                to_events=(AuditEventType.ATTEMPT_STARTED, AuditEventType.EXECUTION_FAILED,
                                           AuditEventType.EXECUTION_TIMED_OUT)),
                AuditTransition(from_event=AuditEventType.CACHE_HIT,
                                to_events=(AuditEventType.EXECUTION_SUCCEEDED, AuditEventType.RESULT_REJECTED)),
            )
            all_events = tuple(AuditEventType)
            field_rules = (
                AuditFieldRule(field_name="tool_call_id", required_for_events=all_events),
                AuditFieldRule(field_name="request_hash", required_for_events=all_events, hash_only=True),
                AuditFieldRule(field_name="argument_schema_hash", required_for_events=all_events, hash_only=True),
                AuditFieldRule(field_name="authorization_policy_hash", required_for_events=all_events, hash_only=True),
                AuditFieldRule(field_name="attempt_id", required_for_events=(AuditEventType.ATTEMPT_STARTED, AuditEventType.ATTEMPT_FAILED)),
                AuditFieldRule(field_name="result_hash", required_for_events=(AuditEventType.EXECUTION_SUCCEEDED,), hash_only=True),
                AuditFieldRule(field_name="failure_code", required_for_events=(AuditEventType.ATTEMPT_FAILED, AuditEventType.EXECUTION_FAILED,
                                                                                AuditEventType.EXECUTION_TIMED_OUT, AuditEventType.RESULT_REJECTED)),
                AuditFieldRule(field_name="redacted_fields", required_for_events=all_events, sensitive=True),
            )
            result_contract = {
                "mcp_fields_preserved": ["content", "structuredContent", "isError", "_meta"],
                "structured_content_validated_when_output_schema_declared": True,
                "meta_visibility": "HOST_ONLY",
                "content_trust": "EXTERNAL_UNTRUSTED_CONTENT",
                "tool_error_must_remain_material": True,
                "protocol_error_separate_from_tool_error": True,
                "available_at_required_when_tool_pit_policy_requires": True,
            }
            observability = {
                "span_name": "p3.tool.call",
                "required_dimensions": ["run_id", "cycle_id", "person_id", "tool_id", "provider_id", "tool_call_id"],
                "recommended_attributes": ["gen_ai.operation.name", "gen_ai.tool.name", "server.address", "error.type"],
                "raw_arguments_recording": "FORBIDDEN",
                "raw_result_recording": "FORBIDDEN_BY_DEFAULT",
            }
            base = {
                "run_id": mcp_gateway_policy.run_id, "cycle_id": mcp_gateway_policy.cycle_id,
                "snapshot_id": mcp_gateway_policy.snapshot_id, "as_of_time": mcp_gateway_policy.as_of_time,
                "lineage_id": f"tool_call_audit_contract:{mcp_gateway_policy.content_hash}",
                "status": ArtifactStatus.READY, "gateway_policy_hash": mcp_gateway_policy.content_hash,
                "allowed_event_types": allowed, "terminal_event_types": terminal, "transitions": transitions,
                "field_rules": field_rules,
                "redaction_rules": ("credentials_never_recorded", "arguments_hash_by_default", "result_hash_by_default",
                                    "authorization_headers_redacted", "host_meta_not_exposed_to_model"),
                "forbidden_fields": ("future_return", "candidate_score", "rank_score", "portfolio_weight",
                                     "trade_decision", "buy_sell_signal", "api_key", "access_token", "refresh_token", "password"),
                "result_contract": result_contract, "observability_mapping": observability, "issues": (),
            }
            digest = compute_artifact_hash({"artifact_name": "tool_call_audit_contract", "schema_id": "tool_call_audit_contract.v2",
                                            "schema_version": "2.0.0", "contract_version": "2.0.0",
                                            "fake_success_forbidden": True,
                                            "pre_execution_rejection_belongs_to_request_validation_panel": True, **base})
            artifact = ToolCallAuditContract(artifact_id=f"audit_contract_{digest[:24]}", content_hash=digest, **base)
            self._events.emit("module_succeeded", {**dims, "duration_ms": round((perf_counter()-started)*1000,3),
                              "input_record_count": len(mcp_gateway_policy.controls), "output_record_count": 1,
                              "warning_count": 0, "error_count": 0})
            return artifact
        except Exception:
            self._events.emit("module_failed", {**dims, "duration_ms": round((perf_counter()-started)*1000,3),
                              "input_record_count": len(mcp_gateway_policy.controls), "output_record_count": 0,
                              "warning_count": 0, "error_count": 1})
            raise
