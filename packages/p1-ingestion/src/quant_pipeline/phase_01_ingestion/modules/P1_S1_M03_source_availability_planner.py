from __future__ import annotations

from copy import deepcopy

from ._module_executor import ContractValidationError
from ._p1_semantic_helpers import validate_inputs
from ._s345_semantics import is_optional_source
from ..core import deterministic_id, normalize_domain, normalize_utc_timestamp, stable_digest, timestamp_le


def _local_path(paths, source_id: str, dataset_id: str, source_index: int):
    if isinstance(paths, dict):
        nested = paths.get(source_id)
        if isinstance(nested, dict):
            return nested.get(dataset_id) or nested.get("default")
        return nested or paths.get(dataset_id)
    if isinstance(paths, list) and source_index < len(paths):
        return paths[source_index]
    return None


def _partitions(dataset: dict) -> list[dict]:
    raw = dataset.get("partitions")
    if raw is None:
        return [{"partition_id": dataset.get("partition_id") or "default"}]
    if not isinstance(raw, list) or not raw:
        raise ContractValidationError("dataset partitions must be a non-empty list")
    result = []
    for index, item in enumerate(raw):
        if isinstance(item, str):
            result.append({"partition_id": item})
        elif isinstance(item, dict):
            entry = dict(item)
            entry.setdefault("partition_id", f"partition-{index+1}")
            result.append(entry)
        else:
            raise ContractValidationError("partition must be a string or object")
    return result


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    required = ["validated_ingestion_run_config", "source_registry", "source_calendar_config", "local_raw_file_paths"]
    validate_inputs(inputs, required)
    run = inputs["validated_ingestion_run_config"]
    if not isinstance(run, dict) or not run.get("run_id"):
        raise ContractValidationError("validated_ingestion_run_config must contain run_id")
    registry = inputs["source_registry"]
    sources = registry.get("sources", []) if isinstance(registry, dict) else []
    if not sources:
        raise ContractValidationError("source plan requires at least one source")
    calendar = inputs["source_calendar_config"]
    if not isinstance(calendar, dict) or not calendar:
        raise ContractValidationError("source calendar must be declared")
    paths = inputs["local_raw_file_paths"]

    tasks = []
    seen_task_ids = set()
    tasks_per_source: dict[str, int] = {}
    contract_mode = str(run.get("contract_mode") or "LEGACY_V1").upper()
    for source_index, source in enumerate(sources):
        if not isinstance(source, dict) or not source.get("source_id"):
            raise ContractValidationError("source_id is required")
        if source.get("enabled") is False:
            continue
        source_id = source["source_id"]
        provider = source.get("provider") or source_id
        adapter_id = source.get("adapter_id") or "generic_http"
        datasets = source.get("datasets") or [{"dataset_id": source.get("dataset") or source_id}]
        for dataset in datasets:
            dataset = dict(dataset)
            dataset_id = dataset.get("dataset_id") or dataset.get("dataset") or source_id
            domain, routing_inferred = normalize_domain(
                dataset.get("domain") or source.get("source_category") or source.get("domain"),
                source_type=source.get("source_type"),
            )
            if routing_inferred and config.get("strict_routing"):
                raise ContractValidationError(
                    f"explicit domain/routing is required in strict_routing mode for source={source_id} dataset={dataset_id}"
                )
            for partition in _partitions(dataset):
                partition_id = partition.get("partition_id") or "default"
                requested_start = partition.get("period_start") or dataset.get("period_start") or run.get("start_time")
                requested_end = partition.get("period_end") or dataset.get("period_end") or run.get("end_time")
                reference_time = partition.get("reference_time") or dataset.get("reference_time") or source.get("reference_time")
                available_at = (
                    partition.get("available_at")
                    or dataset.get("available_at")
                    or source.get("available_at")
                )
                # Normalize every declared timestamp before any comparison. strict_temporal
                # controls whether unknown timestamps are allowed; it must never permit
                # naive/aware datetime mixing.
                if reference_time and not (isinstance(reference_time, str) and len(reference_time.strip()) == 10):
                    reference_time = normalize_utc_timestamp(reference_time, field_name="reference_time", allow_none=True)
                available_at = normalize_utc_timestamp(available_at, field_name="available_at", allow_none=True)
                if config.get("strict_temporal") and available_at is None:
                    raise ContractValidationError("available_at is required in strict_temporal mode")
                task_id = deterministic_id(
                    "task",
                    run["run_id"], source_id, dataset_id, partition_id,
                    requested_start, requested_end, reference_time,
                )
                if task_id in seen_task_ids:
                    raise ContractValidationError("task_id collision detected")
                seen_task_ids.add(task_id)
                critical = bool(dataset.get("critical", source.get("critical", source.get("criticality") == "critical")))
                if is_optional_source(source) or is_optional_source(dataset):
                    critical = False
                local_path = partition.get("file_path") or dataset.get("file_path") or source.get("file_path") or _local_path(paths, source_id, dataset_id, source_index)
                request_spec = deepcopy(partition.get("request_spec") or dataset.get("request_spec") or source.get("request_spec") or {})
                if contract_mode == "LEGACY_V1" and isinstance(request_spec, dict) and request_spec.get("pagination"):
                    raise ContractValidationError(
                        "LEGACY_V1 cannot execute paginated requests because downstream legacy contracts cannot represent multiple pages; "
                        "use contract_mode=CAPTURE_V2"
                    )
                task = {
                    "task_id": task_id,
                    "run_id": run["run_id"],
                    "contract_mode": contract_mode,
                    "as_of_time": run.get("as_of_time"),
                    "source_id": source_id,
                    "provider": provider,
                    "adapter_id": adapter_id,
                    "source_type": source.get("source_type", "api"),
                    "source_category": domain,
                    "domain": domain,
                    "routing_inferred": bool(routing_inferred),
                    "dataset": dataset_id,
                    "dataset_id": dataset_id,
                    "partition_id": partition_id,
                    "critical": critical,
                    "criticality": "critical" if critical else "non_critical",
                    "reference_time": reference_time,
                    "available_at": available_at,
                    "declared_available_at": available_at,
                    "requested_period_start": requested_start,
                    "requested_period_end": requested_end,
                    "period_start": requested_start,
                    "period_end": requested_end,
                    "credential_kind": source.get("credential_kind", "NONE"),
                    "credential_handle": source.get("credential_handle"),
                    "credential_handles": deepcopy(source.get("credential_handles") or {}),
                    "credential_required": bool(source.get("credential_kind") not in (None, "NONE") and (source.get("credential_handle") or source.get("credential_handles"))),
                    "request_spec": request_spec,
                    "lineage_id": deterministic_id("lineage-source-capture", run["run_id"], source_id, dataset_id, partition_id),
                    "fixture": bool(source.get("fixture") or dataset.get("fixture")),
                }
                for field in ("authority_role", "required", "required_for_closure", "optional", "criticality"):
                    value = dataset.get(field, source.get(field))
                    if value is not None:
                        task[field] = value
                for field in ("asset", "frequency", "format", "source_url", "expected_sha256", "content_type", "content_encoding"):
                    value = partition.get(field, dataset.get(field, source.get(field)))
                    if value is not None:
                        task[field] = value
                if local_path is not None:
                    task["file_path"] = str(local_path)
                availability_ok = timestamp_le(available_at, run.get("as_of_time"))
                task["available_by_as_of"] = availability_ok
                if availability_ok is False:
                    task["availability_state"] = "FUTURE_RELATIVE_TO_AS_OF"
                    task["eligible_for_capture"] = False
                    task["eligibility_reason"] = "FUTURE_RELATIVE_TO_AS_OF"
                elif availability_ok is True:
                    task["availability_state"] = "AVAILABLE_BY_AS_OF"
                    task["eligible_for_capture"] = True
                else:
                    task["availability_state"] = "UNKNOWN"
                    # Unknown availability is permitted only outside strict temporal mode.
                    # It remains explicit so downstream policy can warn/block without inventing time.
                    task["eligible_for_capture"] = not bool(config.get("strict_temporal"))
                    if not task["eligible_for_capture"]:
                        task["eligibility_reason"] = "AVAILABLE_AT_UNKNOWN"
                tasks.append(task)
                tasks_per_source[source_id] = tasks_per_source.get(source_id, 0) + 1

    if contract_mode == "LEGACY_V1":
        incompatible = sorted(source_id for source_id, count in tasks_per_source.items() if count > 1)
        if incompatible:
            raise ContractValidationError(
                "LEGACY_V1 compatibility permits at most one planned capture per source_id; "
                f"multi-capture sources require contract_mode=CAPTURE_V2 and upgraded S3-S5/P2: {incompatible}"
            )

    tasks.sort(key=lambda row: (row["source_id"], row["dataset_id"], row["partition_id"], row["task_id"]))
    digest = stable_digest(tasks)
    return {
        "module_id": "P1.S1.M03",
        "module_name": "source_availability_planner",
        "phase": "phase_01_ingestion",
        "subphase": "P1.S1",
        "contract": "P1_S1_M03_source_availability_planner.yaml",
        "required_inputs": required,
        "outputs": {"source_capture_plan": {
            "artifact_id": f"source_capture_plan-{digest[:12]}",
            "created_at": config.get("created_at", "2024-01-01T00:00:00Z"),
            "lineage_id": f"lineage-source-capture-plan-{digest[:12]}",
            "pipeline_version": config.get("pipeline_version", "V14.1-RC4.1"),
            "schema_version": "2",
            "run_id": run["run_id"],
            "as_of_time": run.get("as_of_time"),
            "contract_mode": contract_mode,
            "tasks": tasks,
            "critical_sources_marked": True,
            "task_count": len(tasks),
        }},
    }
