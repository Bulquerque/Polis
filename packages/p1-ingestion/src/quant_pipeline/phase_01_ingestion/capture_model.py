from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from .core import deterministic_id, sanitize_url


@dataclass(frozen=True)
class RawCaptureEnvelope:
    capture_id: str
    run_id: str | None
    task_id: str
    source_id: str
    provider: str
    adapter_id: str
    dataset_id: str
    domain: str
    request_id: str
    partition_id: str | None
    page_id: str | None
    requested_at: str | None
    retrieved_at: str | None
    reference_time: str | None
    declared_available_at: str | None
    capture_state: str
    lineage_id: str
    contract_mode: str = "LEGACY_V1"
    request_method: str | None = None
    sanitized_url: str | None = None
    http_status: int | None = None
    content_type: str | None = None
    content_encoding: str | None = None
    retry_count: int = 0
    quota_metadata: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_capture_id(task: dict, *, page_id: str | None = None, attempt: int = 1) -> str:
    return deterministic_id(
        "capture",
        task.get("run_id"), task.get("task_id"), task.get("source_id"),
        task.get("dataset_id"), task.get("partition_id"), page_id, attempt,
    )


def make_request_id(task: dict, *, page_id: str | None = None, attempt: int = 1) -> str:
    return deterministic_id(
        "request",
        task.get("task_id"), task.get("source_id"), task.get("dataset_id"),
        task.get("request_spec"), page_id, attempt,
    )


def envelope_from_task(
    task: dict,
    *,
    state: str,
    page_id: str | None = None,
    attempt: int = 1,
    requested_at: str | None = None,
    retrieved_at: str | None = None,
    http_status: int | None = None,
    content_type: str | None = None,
    content_encoding: str | None = None,
    retry_count: int = 0,
    error_code: str | None = None,
    error_message: str | None = None,
) -> RawCaptureEnvelope:
    request_spec = task.get("request_spec") if isinstance(task.get("request_spec"), dict) else {}
    return RawCaptureEnvelope(
        capture_id=make_capture_id(task, page_id=page_id, attempt=attempt),
        run_id=task.get("run_id"),
        task_id=task["task_id"],
        source_id=task["source_id"],
        provider=task.get("provider") or task["source_id"],
        adapter_id=task.get("adapter_id") or "local_file",
        dataset_id=task.get("dataset_id") or task.get("dataset") or task["source_id"],
        domain=task.get("domain") or task.get("source_category") or "benchmark",
        request_id=make_request_id(task, page_id=page_id, attempt=attempt),
        partition_id=task.get("partition_id"),
        page_id=page_id,
        requested_at=requested_at,
        retrieved_at=retrieved_at,
        reference_time=task.get("reference_time"),
        declared_available_at=task.get("declared_available_at") or task.get("available_at"),
        capture_state=state,
        lineage_id=task.get("lineage_id") or deterministic_id("lineage", task),
    contract_mode=str(task.get("contract_mode") or "LEGACY_V1").upper(),
        request_method=str(request_spec.get("method") or "GET").upper() if request_spec else None,
        sanitized_url=sanitize_url(request_spec.get("url") or task.get("source_url")),
        http_status=http_status,
        content_type=content_type,
        content_encoding=content_encoding,
        retry_count=retry_count,
        quota_metadata=None,
        error_code=error_code,
        error_message=error_message,
    )
