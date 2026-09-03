from __future__ import annotations

from ._module_executor import _stable_digest
from ..core import identity_digest
from ._p1_semantic_helpers import tasks_from_manifest, validate_inputs
from ._s345_semantics import resolve_run_id, stable_id


_RETRYABLE = {"RATE_LIMITED", "QUOTA_EXHAUSTED", "TIMEOUT", "CONNECTION_ERROR", "DNS_ERROR", "TLS_ERROR", "HTTP_5XX", "PROVIDER_UNAVAILABLE"}


def _error_for_result(result: dict, task: dict, run_id: str | None, created_at: str, pipeline_version: str) -> dict:
    state = str(result.get("final_state") or "FAILED_NON_BLOCKING")
    issue_codes = result.get("readability_issue_codes") or []
    code = result.get("error_code") or (issue_codes[0] if issue_codes else None)

    if state in {"SUCCESS", "SKIPPED", "NOT_APPLICABLE"} and not code:
        return {
            "error_id": stable_id("error-state", {"task_id": task.get("task_id"), "state": "NO_ERROR"}),
            "ingestion_run_id": run_id,
            "task_id": task.get("task_id"),
            "source_id": task.get("source_id"),
            "dataset_id": task.get("dataset_id") or task.get("dataset"),
            "error_flag": False,
            "error_severity": "none",
            "error_code": "NO_ERROR",
            "error_message": "No error reported",
            "is_blocking": False,
            "retryable": False,
            "created_at": created_at,
            "lineage_id": task.get("lineage_id"),
            "pipeline_version": pipeline_version,
        }

    normalized = str(code or state or "INGESTION_FAILURE").upper()
    if normalized in {"INVALID_JSON", "INVALID_XML", "HTML_SAVED_AS_CSV", "EMPTY_FILE", "INVALID_PARQUET_CONTAINER"}:
        family = "INVALID_CONTENT"
    elif normalized in {"ARCHIVE_CORRUPTION", "GZIP_CORRUPTION"}:
        family = "ARCHIVE_CORRUPTION"
    elif state in {"RATE_LIMITED", "QUOTA_EXHAUSTED", "UNAVAILABLE"}:
        family = state
    elif normalized == "CAPTURE_MISSING":
        family = "CAPTURE_MISSING"
    else:
        family = normalized

    blocking = bool(result.get("is_blocking")) or state == "FAILED_BLOCKING"
    severity = "critical" if blocking else "warning" if state in {"PARTIAL", "RATE_LIMITED", "UNAVAILABLE"} else "error"
    return {
        "error_id": stable_id("error", {"task_id": task.get("task_id"), "state": state, "code": family}),
        "ingestion_run_id": run_id,
        "task_id": task.get("task_id"),
        "source_id": task.get("source_id"),
        "dataset_id": task.get("dataset_id") or task.get("dataset"),
        "error_flag": True,
        "error_severity": severity,
        "error_code": family,
        "provider_error_code": code,
        "error_message": result.get("provider_error_message") or f"Ingestion task ended with state={state} code={family}",
        "retry_count": int(result.get("retry_count") or 0),
        "http_status": result.get("http_status"),
        "is_blocking": blocking,
        "retryable": family in _RETRYABLE or state in _RETRYABLE,
        "created_at": created_at,
        "lineage_id": task.get("lineage_id"),
        "pipeline_version": pipeline_version,
    }


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    required = ["ingestion_manifest", "raw_readability_report", "capture_task_manifest"]
    validate_inputs(inputs, required)

    manifest = inputs["ingestion_manifest"] if isinstance(inputs["ingestion_manifest"], dict) else {}
    tasks = tasks_from_manifest(inputs["capture_task_manifest"])
    results = {
        str(item.get("task_id")): item
        for item in manifest.get("task_results", [])
        if isinstance(item, dict) and item.get("task_id")
    }
    run_id = resolve_run_id(config, manifest=manifest, records=results.values())
    created_at = config.get("created_at", "2024-01-01T00:00:00Z")
    pipeline_version = config.get("pipeline_version", "V14.1-RC4.1")

    errors = []
    for task in tasks:
        result = results.get(str(task.get("task_id"))) or {
            "final_state": "FAILED_BLOCKING" if task.get("critical") else "FAILED_NON_BLOCKING",
            "is_blocking": bool(task.get("critical")),
            "error_code": "MANIFEST_RESULT_MISSING",
        }
        errors.append(_error_for_result(result, task, run_id, created_at, pipeline_version))

    digest = identity_digest(errors)
    report = {
        "artifact_id": f"ingestion-errors-{digest[:12]}",
        "created_at": created_at,
        "lineage_id": f"lineage-ingestion-errors-{digest[:12]}",
        "pipeline_version": pipeline_version,
        "ingestion_run_id": run_id,
        "errors": errors,
        "error_count": sum(1 for error in errors if error.get("error_flag")),
        "blocking_error_count": sum(1 for error in errors if error.get("is_blocking")),
        "no_silent_failure": True,
    }
    return {
        "module_id": "P1.S5.M03",
        "module_name": "ingestion_error_report_builder",
        "phase": "phase_01_ingestion",
        "subphase": "P1.S5",
        "contract": "P1_S5_M03_ingestion_error_report_builder.yaml",
        "required_inputs": required,
        "outputs": {"ingestion_error_report": report},
    }
