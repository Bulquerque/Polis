"""Pure helpers and process-local types for the P3.S40 gateway."""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash, utc
from quant_pipeline.phase_03_agents_rag_memory.runtime_shared.s21_models import (
    ToolExecutionStatus, ValidatedToolCallRequestRecord,
)

from .models import ResearchToolExecutionTraceRecord
from .registry import AliasResolution, ExecutableOperation


@dataclass(frozen=True, slots=True)
class GatewayInvocationContext:
    request_id: str
    person_id: str
    decision_time: datetime
    snapshot_id: str
    deterministic_seed: int
    execution_profile: str
    run_id: str = "runtime"
    cycle_id: str = "runtime"
    cognition_transaction_id: str = "runtime"


@dataclass(frozen=True, slots=True)
class PreparedInvocation:
    operation: ExecutableOperation
    resolution: AliasResolution
    provider_id: str
    parsed_request: BaseModel
    context: GatewayInvocationContext
    trace_id: str


class TraceSinkPort(Protocol):
    def emit(self, record: ResearchToolExecutionTraceRecord) -> None:
        """Persist or collect one immutable trace event."""


class InMemoryTraceSink:
    def __init__(self) -> None:
        self.records: list[ResearchToolExecutionTraceRecord] = []

    def emit(self, record: ResearchToolExecutionTraceRecord) -> None:
        self.records.append(record)


def validate_result(operation: ExecutableOperation, raw_result: object) -> BaseModel:
    if isinstance(raw_result, BaseModel):
        payload = raw_result.model_dump(mode="json")
    elif isinstance(raw_result, Mapping):
        payload = dict(raw_result)
    else:
        raise TypeError("handler result must be a Pydantic model or mapping")
    return operation.result_model.model_validate_json(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def evidence_ids(payload: Mapping[str, object]) -> tuple[str, ...]:
    raw = payload.get("evidence_refs", ())
    ids: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                ids.append(item)
            elif isinstance(item, Mapping) and isinstance(item.get("evidence_id"), str):
                ids.append(str(item["evidence_id"]))
    records = payload.get("records", ())
    if isinstance(records, list):
        for item in records:
            if isinstance(item, Mapping) and isinstance(item.get("record_id"), str):
                ids.append(str(item["record_id"]))
    return tuple(sorted(set(ids)))


def available_at(payload: Mapping[str, object], fallback: datetime) -> datetime:
    value = payload.get("latest_available_at")
    if isinstance(value, str):
        return utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    if isinstance(value, datetime):
        return utc(value)
    records = payload.get("records", ())
    candidates: list[datetime] = []
    if isinstance(records, list):
        for item in records:
            if not isinstance(item, Mapping):
                continue
            record_time = item.get("available_at")
            if isinstance(record_time, str):
                candidates.append(utc(datetime.fromisoformat(record_time.replace("Z", "+00:00"))))
            elif isinstance(record_time, datetime):
                candidates.append(utc(record_time))
    return max(candidates) if candidates else utc(fallback)


def cost_units(payload: Mapping[str, object]) -> float:
    execution = payload.get("execution", {})
    if isinstance(execution, Mapping) and isinstance(execution.get("cost_units"), (int, float)):
        return float(execution["cost_units"])
    mode = str(payload.get("executed_mode", "BASIC"))
    return {"BASIC": 1.0, "LOOKUP": 1.0, "ROBUST": 2.0, "STANDARD": 2.0}.get(mode, 3.0)


def failure_status(exc: Exception) -> ToolExecutionStatus:
    name = type(exc).__name__.upper()
    if "TEMPORAL" in name or "FUTURE" in str(exc).upper() or "MATURE" in name:
        return ToolExecutionStatus.REJECTED_TEMPORAL
    return ToolExecutionStatus.FAILED_PROVIDER


def failure_code(exc: Exception) -> str:
    return (
        "P3RT-PIT-HANDLER-TEMPORAL-REJECTION"
        if failure_status(exc) is ToolExecutionStatus.REJECTED_TEMPORAL
        else "P3RT-HANDLER-EXECUTION-FAILED"
    )


def trace_id(request: ValidatedToolCallRequestRecord, operation: ExecutableOperation) -> str:
    return content_hash({
        "request_id": request.request.tool_call_request_id,
        "tool_id": operation.descriptor.tool_id,
        "operation_id": operation.descriptor.operation_id,
    })[:32]


def trace_record(
    event_name: str,
    trace: str,
    request: ValidatedToolCallRequestRecord,
    operation: ExecutableOperation,
    attributes: Mapping[str, object] | None,
) -> ResearchToolExecutionTraceRecord:
    payload = {
        "trace_id": trace,
        "span_id": content_hash({"trace_id": trace, "event": event_name})[:16],
        "event_name": event_name,
        "event_time": utc(request.request.requested_at),
        "cognition_transaction_id": request.request.cognition_transaction_id,
        "request_id": request.request.tool_call_request_id,
        "execution_id": f"pending:{request.request.tool_call_request_id}",
        "tool_id": operation.descriptor.tool_id,
        "operation_id": operation.descriptor.operation_id,
        "attributes": dict(attributes or {}),
    }
    return ResearchToolExecutionTraceRecord(**payload, event_hash=content_hash(payload))
