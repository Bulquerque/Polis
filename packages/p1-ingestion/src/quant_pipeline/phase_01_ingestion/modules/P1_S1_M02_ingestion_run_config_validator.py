from __future__ import annotations

from ._module_executor import ContractValidationError
from ..core import (
    ensure_no_source_placeholder,
    normalize_contract_mode,
    normalize_utc_timestamp,
    reject_forbidden_fields,
    reject_materialized_secrets,
    stable_digest,
    timestamp_le,
    validate_timezone_name,
)

ALLOWED_MODES = {"HISTORICAL", "INCREMENTAL", "LIVE"}


def _declared_credential_handles(value: dict) -> set[str]:
    handles: set[str] = set()
    for key in ("allowed_handles", "handles", "credential_handles"):
        raw = value.get(key)
        if isinstance(raw, str):
            handles.add(raw)
        elif isinstance(raw, (list, tuple, set)):
            handles.update(str(item) for item in raw if item)
        elif isinstance(raw, dict):
            handles.update(str(item) for item in raw.values() if item)
    return handles


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    required = ["ingestion_run_config", "source_credentials_handle", "source_calendar_config", "source_registry"]
    missing = [name for name in required if name not in inputs]
    if missing:
        raise ContractValidationError(f"missing required inputs: {missing}")
    reject_forbidden_fields(inputs)
    ensure_no_source_placeholder(inputs)
    reject_materialized_secrets(inputs["source_credentials_handle"])

    run_config = inputs["ingestion_run_config"]
    if not isinstance(run_config, dict):
        raise ContractValidationError("ingestion_run_config must be an object")
    run_id = run_config.get("run_id")
    if not run_id or not isinstance(run_id, str):
        raise ContractValidationError("run_id is required")
    mode = str(run_config.get("mode") or "HISTORICAL").upper()
    if mode not in ALLOWED_MODES:
        raise ContractValidationError(f"mode not allowed: {mode}")

    calendar = inputs["source_calendar_config"]
    if not isinstance(calendar, dict) or not calendar:
        raise ContractValidationError("source calendar must be declared")

    as_of_raw = run_config.get("as_of_time") or config.get("as_of_time") or config.get("created_at")
    as_of_time = normalize_utc_timestamp(as_of_raw, field_name="as_of_time", allow_none=not config.get("strict_temporal"))
    start_time = normalize_utc_timestamp(run_config.get("start_time"), field_name="start_time", allow_none=True)
    end_time = normalize_utc_timestamp(run_config.get("end_time"), field_name="end_time", allow_none=True)
    if start_time and end_time and timestamp_le(start_time, end_time) is False:
        raise ContractValidationError("start_time must not be after end_time")

    timezone_name = validate_timezone_name(run_config.get("timezone") or "UTC")
    contract_mode = normalize_contract_mode(run_config.get("contract_mode") or config.get("contract_mode"))
    if contract_mode == "LEGACY_V1" and str(config.get("release_scope", "")).upper() == "P1_TECHNICAL_CLOSURE":
        raise ContractValidationError("LEGACY_V1 is historical compatibility only and cannot execute in the active P1 gate")
    retry_policy = run_config.get("retry_policy") or {}
    concurrency_policy = run_config.get("concurrency_policy") or {}
    provider_budgets = run_config.get("provider_budgets") or {}
    if not isinstance(retry_policy, dict) or not isinstance(concurrency_policy, dict) or not isinstance(provider_budgets, dict):
        raise ContractValidationError("retry_policy, concurrency_policy and provider_budgets must be objects")
    max_workers = int(concurrency_policy.get("max_workers", 1) or 1)
    if max_workers < 1:
        raise ContractValidationError("concurrency_policy.max_workers must be >= 1")
    if max_workers > 1 and not config.get("enable_experimental_concurrency"):
        raise ContractValidationError(
            "concurrency_policy.max_workers > 1 is not enabled in the compatibility-first runtime; "
            "use max_workers=1 unless experimental concurrency is explicitly enabled"
        )

    storage_config = run_config.get("storage") or {}
    if not storage_config and config.get("artifact_root"):
        storage_config = {"backend": "local", "root": str(config["artifact_root"])}
    if storage_config and not isinstance(storage_config, dict):
        raise ContractValidationError("storage must be an object")

    credential_context = inputs["source_credentials_handle"]
    if not isinstance(credential_context, dict):
        raise ContractValidationError("source_credentials_handle must be an object")
    allowed_handles = _declared_credential_handles(credential_context)
    if allowed_handles and isinstance(inputs.get("source_registry"), dict):
        for source in inputs["source_registry"].get("sources", []):
            if not isinstance(source, dict):
                continue
            referenced = []
            if source.get("credential_handle"):
                referenced.append(str(source["credential_handle"]))
            if isinstance(source.get("credential_handles"), dict):
                referenced.extend(str(v) for v in source["credential_handles"].values() if v)
            unknown = sorted(set(referenced) - allowed_handles)
            if unknown:
                raise ContractValidationError(f"credential handle is not declared in source_credentials_handle: {unknown}")

    semantic = {
        "run_id": run_id,
        "mode": mode,
        "as_of_time": as_of_time,
        "start_time": start_time,
        "end_time": end_time,
        "timezone": timezone_name,
        "contract_mode": contract_mode,
        "retry_policy": retry_policy,
        "concurrency_policy": concurrency_policy,
        "provider_budgets": provider_budgets,
        "allow_partial_success": bool(run_config.get("allow_partial_success", False)),
        "storage": storage_config,
        "calendar_id": calendar.get("calendar_id"),
        "registry_content_hash": inputs["source_registry"].get("registry_content_hash") if isinstance(inputs["source_registry"], dict) else None,
    }
    digest = stable_digest(semantic)
    return {
        "module_id": "P1.S1.M02",
        "module_name": "ingestion_run_config_validator",
        "phase": "phase_01_ingestion",
        "subphase": "P1.S1",
        "contract": "P1_S1_M02_ingestion_run_config_validator.yaml",
        "required_inputs": required,
        "outputs": {"validated_ingestion_run_config": {
            "artifact_id": f"validated_ingestion_run_config-{digest[:12]}",
            "created_at": config.get("created_at", "2024-01-01T00:00:00Z"),
            "lineage_id": f"lineage-validated-ingestion-{digest[:12]}",
            "pipeline_version": config.get("pipeline_version", "V14.1-RC4.1"),
            "schema_version": "2",
            **semantic,
            "credentials_materialized": False,
            "credential_context_declared": bool(credential_context),
            "calendar_declared": True,
        }},
    }
