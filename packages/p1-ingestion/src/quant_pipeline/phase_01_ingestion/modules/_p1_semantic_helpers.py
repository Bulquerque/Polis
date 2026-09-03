from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from ._module_executor import ContractValidationError, _stable_digest
from ..capture_model import envelope_from_task
from ..core import (
    FORBIDDEN_ECONOMIC_FIELDS as FORBIDDEN,
    deterministic_id,
    identity_digest,
    reject_forbidden_fields,
    sanitize_url,
    ensure_no_source_placeholder,
)
from ..providers import AdapterConfigurationError, AdapterContext, resolve_adapter
from ..transport import CredentialResolutionError, CredentialResolver, HttpClient, TransportError


def validate_inputs(inputs: dict, required: list[str]) -> None:
    missing = [name for name in required if name not in inputs]
    if missing:
        raise ContractValidationError(f"missing required inputs: {missing}")
    reject_forbidden_fields(inputs)
    ensure_no_source_placeholder(inputs)


def tasks_from_manifest(value):
    if isinstance(value, dict) and isinstance(value.get("tasks"), list):
        return value["tasks"]
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and value.get("source"):
        raise ContractValidationError("capture_task_manifest cannot be synthesized from source")
    raise ContractValidationError("capture_task_manifest must contain tasks")


def metadata(artifact: str, payload, config: dict) -> dict:
    digest = identity_digest(payload)
    return {
        "artifact_id": f"{artifact}-{digest[:12]}",
        "created_at": config.get("created_at", "2024-01-01T00:00:00Z"),
        "lineage_id": f"lineage-{artifact}-{digest[:12]}",
        "pipeline_version": config.get("pipeline_version", "V14.1-RC4.1"),
        "schema_version": "2",
    }


class _ProviderBudgetHttpClient:
    def __init__(self, base, *, provider: str, config: dict):
        self.base = base
        self.provider = str(provider)
        self.config = config

    def request(self, *args, **kwargs):
        budgets = self.config.get("provider_budgets") or {}
        raw_budget = budgets.get(self.provider) or budgets.get(self.provider.lower())
        if isinstance(raw_budget, dict):
            limit = raw_budget.get("max_requests")
            if limit is None:
                limit = raw_budget.get("request_limit")
        else:
            limit = raw_budget
        counts = self.config.setdefault("_provider_request_counts", {})
        current = int(counts.get(self.provider, 0))
        if limit is not None and current >= int(limit):
            raise TransportError("provider request budget exhausted", code="QUOTA_EXHAUSTED", retry_count=0)
        counts[self.provider] = current + 1
        return self.base.request(*args, **kwargs)


def raw_inventory(
    artifact: str,
    inputs: dict,
    config: dict,
    *,
    text_allowed: bool = False,
    source_categories: set[str] | None = None,
) -> dict:
    """Capture raw payloads while preserving legacy records for downstream compatibility.

    Successful captures are emitted in ``records`` so current S3-S5 continue to work.
    Every attempt, including failures, is emitted in ``attempts`` for the upgraded S5.
    """
    tasks = tasks_from_manifest(inputs["capture_task_manifest"])
    records: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    resolver = CredentialResolver(config.get("environment") if isinstance(config.get("environment"), dict) else None)
    http_client = config.get("http_client") or config.get("_http_client_runtime")
    if http_client is None:
        http_client = HttpClient(
            timeout=float(config.get("http_timeout", 30.0)),
            max_retries=int(config.get("http_max_retries", 3)),
            backoff_base=float(config.get("http_backoff_base", 0.5)),
            allow_insecure_http=bool(config.get("allow_insecure_http", False)),
            max_response_bytes=int(config.get("http_max_response_bytes", 256 * 1024 * 1024)),
        )
        config["_http_client_runtime"] = http_client

    for task in tasks:
        if not isinstance(task, dict) or not task.get("source_id"):
            raise ContractValidationError("source_id is required for every raw capture")
        category = task.get("source_category") or task.get("domain")
        if source_categories and category and category not in source_categories:
            continue

        # Point-in-time fail-closed gate. A task known to be unavailable at the
        # run cutoff is never fetched and can never enter the P2 handoff.
        if task.get("available_by_as_of") is False or task.get("eligible_for_capture") is False:
            skipped = dict(task)
            skipped.setdefault("task_id", deterministic_id("task", skipped.get("source_id"), skipped.get("lineage_id")))
            skipped.setdefault("dataset_id", skipped.get("dataset") or skipped.get("source_id"))
            skipped.setdefault("domain", category or next(iter(source_categories or {"benchmark"})))
            state = "UNAVAILABLE" if skipped.get("critical") else "SKIPPED"
            attempts.append(envelope_from_task(
                skipped,
                state=state,
                error_code=skipped.get("eligibility_reason") or skipped.get("availability_state") or "NOT_AVAILABLE_AS_OF",
                error_message="source data is not eligible at the declared as_of_time",
            ).to_dict())
            continue

        if config.get("qualification_positive_path") and task.get("fixture"):
            raise ContractValidationError("synthetic fixture is forbidden in qualification positive path")

        task = dict(task)
        adapter_was_declared = bool(task.get("adapter_id"))
        task.setdefault("task_id", deterministic_id("task", task.get("source_id"), task.get("lineage_id")))
        task.setdefault("dataset_id", task.get("dataset") or task.get("source_id"))
        task.setdefault("domain", category or next(iter(source_categories or {"benchmark"})))
        task.setdefault("adapter_id", task.get("adapter_id") or ("b3" if task.get("domain") == "b3" else None))

        if not any((task.get("raw_bytes") is not None, text_allowed and task.get("raw_text") is not None, task.get("file_path"), task.get("fixture"), task.get("request_spec"), task.get("source_url"), adapter_was_declared)):
            raise ContractValidationError("raw content must be preserved")

        try:
            task_context = AdapterContext(
                credential_resolver=resolver,
                http_client=_ProviderBudgetHttpClient(http_client, provider=task.get("provider") or task.get("source_id"), config=config),
            )
            captured = _capture_task(task, context=task_context, text_allowed=text_allowed, config=config)
            contract_mode = str(task.get("contract_mode") or config.get("contract_mode") or "LEGACY_V1").upper()
            if contract_mode == "LEGACY_V1" and len(captured) > 1:
                raise ContractValidationError(
                    "LEGACY_V1 downstream compatibility cannot represent multiple captures/pages for one task; "
                    "use contract_mode=CAPTURE_V2 only with upgraded S3-S5/P2"
                )
        except (TransportError, AdapterConfigurationError, CredentialResolutionError) as exc:
            code = getattr(exc, "code", None) or "PROVIDER_UNAVAILABLE"
            state = "RATE_LIMITED" if code == "RATE_LIMITED" else "FAILED_BLOCKING" if task.get("critical") else "FAILED_NON_BLOCKING"
            envelope = envelope_from_task(
                task,
                state=state,
                error_code=code,
                error_message=str(exc),
                retry_count=int(getattr(exc, "retry_count", 0) or 0),
                http_status=getattr(exc, "status", None),
            ).to_dict()
            attempts.append(envelope)
            continue

        for page_index, item in enumerate(captured, start=1):
            page_id = item.get("page_id") or (str(page_index) if len(captured) > 1 else task.get("page_id"))
            raw_bytes = item.get("content")
            source_path = item.get("source_path")
            if raw_bytes is None and source_path:
                source_path_obj = Path(source_path)
                digest = sha256()
                byte_count = 0
                with source_path_obj.open("rb") as handle:
                    prefix = handle.read(256)
                    digest.update(prefix)
                    byte_count += len(prefix)
                    while True:
                        chunk = handle.read(1024 * 1024)
                        if not chunk:
                            break
                        digest.update(chunk)
                        byte_count += len(chunk)
                exact_hash = digest.hexdigest()
            else:
                if not isinstance(raw_bytes, (bytes, bytearray)):
                    raise ContractValidationError("raw capture must provide exact bytes or a file-backed source path")
                raw_bytes = bytes(raw_bytes)
                prefix = raw_bytes[:256]
                byte_count = len(raw_bytes)
                exact_hash = sha256(raw_bytes).hexdigest()
            expected_hash = task.get("expected_sha256")
            if expected_hash and exact_hash.lower() != str(expected_hash).lower():
                raise ContractValidationError("raw source hash does not match frozen provenance")
            if str(task.get("format", "")).lower() == "csv" and prefix.lstrip().lower().startswith((b"<!doctype html", b"<html")):
                raise ContractValidationError("HTML response cannot be accepted as CSV")

            envelope = envelope_from_task(
                task,
                state="SUCCESS",
                page_id=page_id,
                requested_at=item.get("requested_at"),
                retrieved_at=item.get("retrieved_at"),
                http_status=item.get("http_status"),
                content_type=item.get("content_type"),
                content_encoding=item.get("content_encoding"),
                retry_count=int(item.get("retry_count", 0)),
            ).to_dict()
            envelope["page_index"] = page_index
            if item.get("response_url"):
                envelope["sanitized_url"] = item["response_url"]
            attempts.append(dict(envelope))
            record = {
                **envelope,
                # Compatibility fields consumed by the current S3-S5 implementation.
                "source_id": task["source_id"],
                "task_id": task.get("task_id"),
                "available_at": task.get("declared_available_at") or task.get("available_at"),
                "source_category": task.get("source_category") or task.get("domain"),
                "dataset": task.get("dataset_id") or task.get("dataset"),
                "dataset_id": task.get("dataset_id") or task.get("dataset") or task["source_id"],
                "asset": task.get("asset"),
                "frequency": task.get("frequency"),
                "period_start": task.get("period_start") or task.get("requested_period_start"),
                "period_end": task.get("period_end") or task.get("requested_period_end"),
                "format": task.get("format"),
                "source_url": sanitize_url(envelope.get("sanitized_url") or task.get("source_url")),
                "expected_sha256": expected_hash,
                "source_file_name": Path(source_path).name if source_path else task.get("source_file_name"),
                "source_file_path": str(source_path) if source_path else None,
                "byte_count": byte_count,
                "raw_preserved": True,
                "raw_content_sha256": exact_hash,
                "cleaning_applied": False,
                "lineage_id": task.get("lineage_id"),
                "capture_state": "SUCCESS",
                "contract_mode": str(task.get("contract_mode") or config.get("contract_mode") or "LEGACY_V1").upper(),
                "page_index": page_index,
            }
            if raw_bytes is not None:
                record["raw_bytes"] = raw_bytes
            records.append(record)

    return {
        **metadata(artifact, {"records": records, "attempts": attempts}, config),
        "records": records,
        "attempts": attempts,
        "raw_preserved": True,
        "cleaning_applied": False,
    }


def _capture_task(task: dict, *, context: AdapterContext, text_allowed: bool, config: dict) -> list[dict]:
    raw = task.get("raw_bytes")
    if raw is None and text_allowed:
        raw = task.get("raw_text")
    if raw is not None:
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        if not isinstance(raw, (bytes, bytearray)):
            raise ContractValidationError("raw content must be exact bytes or explicit text")
        if not raw:
            raise ContractValidationError("raw content must be preserved")
        now = _now(config)
        return [{
            "content": bytes(raw),
            "requested_at": task.get("requested_at") or now,
            "retrieved_at": task.get("retrieved_at") or now,
            "http_status": None,
            "content_type": task.get("content_type"),
            "content_encoding": task.get("content_encoding"),
            "retry_count": 0,
            "source_path": None,
        }]

    if task.get("file_path"):
        source_path = Path(task["file_path"])
        if not source_path.is_file():
            raise ContractValidationError(f"raw source file does not exist: {source_path}")
        if source_path.stat().st_size <= 0:
            raise ContractValidationError("raw content must be preserved")
        now = _now(config)
        return [{
            "content": None,
            "requested_at": task.get("requested_at") or now,
            "retrieved_at": task.get("retrieved_at") or now,
            "http_status": None,
            "content_type": task.get("content_type"),
            "content_encoding": task.get("content_encoding"),
            "retry_count": 0,
            "source_path": str(source_path),
        }]

    if task.get("fixture"):
        now = _now(config)
        return [{
            "content": b"fixture",
            "requested_at": now,
            "retrieved_at": now,
            "http_status": None,
            "content_type": "application/octet-stream",
            "content_encoding": None,
            "retry_count": 0,
            "source_path": None,
        }]

    adapter = resolve_adapter(task.get("adapter_id"))
    if adapter is None:
        raise ContractValidationError("raw content must be preserved or a registered adapter/request must be declared")
    if config.get("perform_health_check") and not adapter.health_check(task, context):
        raise AdapterConfigurationError(f"{adapter.adapter_id} health check failed")
    responses = adapter.fetch_raw(task, context)
    captured = []
    for response in responses:
        captured.append({
            "content": response.content,
            "requested_at": response.requested_at,
            "retrieved_at": response.retrieved_at,
            "http_status": response.status,
            "content_type": response.headers.get("content-type"),
            "content_encoding": response.headers.get("content-encoding"),
            "retry_count": response.retry_count,
            "source_path": None,
            "response_url": response.url,
        })
    if not captured:
        raise ContractValidationError("adapter returned no raw captures")
    return captured


def _now(config: dict) -> str:
    value = config.get("created_at")
    if value:
        return value
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def records_from_artifact(value, artifact: str):
    if isinstance(value, dict) and isinstance(value.get("records"), list):
        return value["records"]
    if isinstance(value, dict) and isinstance(value.get("snapshots"), list):
        return value["snapshots"]
    if isinstance(value, dict) and isinstance(value.get("errors"), list):
        return value["errors"]
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and value.get("source"):
        raise ContractValidationError(f"{artifact} cannot be synthesized from source")
    raise ContractValidationError(f"{artifact} must contain records")


def merge_raw_inventories(artifact: str, values: list, config: dict) -> dict:
    records = []
    attempts = []
    seen_capture_ids = set()
    legacy_seen = set()
    for value in values:
        if isinstance(value, dict) and isinstance(value.get("attempts"), list):
            attempts.extend(dict(item) for item in value["attempts"] if isinstance(item, dict))
        for record in records_from_artifact(value, artifact):
            if not isinstance(record, dict) or not record.get("source_id"):
                raise ContractValidationError("source_id is required")
            if record.get("cleaning_applied"):
                raise ContractValidationError("raw inventory must not be cleaned")
            capture_id = record.get("capture_id")
            if capture_id:
                if capture_id in seen_capture_ids:
                    raise ContractValidationError("capture_id must be unique in aggregate")
                seen_capture_ids.add(capture_id)
            else:
                # Compatibility for legacy fixtures without capture_id.
                legacy_key = (record.get("source_id"), record.get("task_id"), record.get("lineage_id"))
                if legacy_key in legacy_seen:
                    raise ContractValidationError("legacy capture identity must be unique in aggregate")
                legacy_seen.add(legacy_key)
                record = dict(record)
                record["capture_id"] = deterministic_id("capture-legacy", legacy_key)
            records.append(dict(record))
    records.sort(key=lambda row: (
        str(row.get("source_id", "")), str(row.get("dataset_id") or row.get("dataset") or ""),
        str(row.get("task_id", "")), str(row.get("partition_id", "")),
        str(row.get("page_id", "")), str(row.get("capture_id", "")),
    ))
    return {
        **metadata(artifact, {"records": records, "attempts": attempts}, config),
        "records": records,
        "attempts": attempts,
        "raw_preserved": True,
        "cleaning_applied": False,
        "all_sources_accounted": True,
    }
