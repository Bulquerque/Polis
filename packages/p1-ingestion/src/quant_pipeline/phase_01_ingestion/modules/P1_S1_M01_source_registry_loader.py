from __future__ import annotations

from copy import deepcopy

from ._module_executor import ContractValidationError
from ..core import (
    CREDENTIAL_KINDS,
    SOURCE_TYPES,
    deep_copy_without_secret_material,
    normalize_dataset_entries,
    normalize_domain,
    reject_forbidden_fields,
    reject_materialized_secrets,
    stable_digest,
    validate_credential_handle_values,
)
from ..providers import registered_adapter_ids, normalize_adapter_id


def _records(value, fallback_id: str):
    if isinstance(value, dict) and isinstance(value.get("sources"), list):
        return value["sources"]
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and value.get("source_id"):
        return [value]
    if isinstance(value, dict) and value.get("source"):
        raise ContractValidationError("source definitions cannot be synthesized from source")
    raise ContractValidationError(f"source definitions must contain sources: {fallback_id}")


def _default_adapter_id(source: dict, *, strict_adapter_ids: bool = False) -> tuple[str, bool]:
    explicit = source.get("adapter_id") or source.get("adapter")
    if explicit:
        adapter_id = normalize_adapter_id(str(explicit))
        registered = adapter_id in registered_adapter_ids()
        if strict_adapter_ids and not registered:
            raise ContractValidationError(f"adapter_id is not registered: {adapter_id}")
        return adapter_id, registered
    source_id = str(source.get("source_id", "")).lower()
    aliases = {
        "london_strategic_edge": "lse",
        "financial_modeling_prep": "fmp",
    }
    candidate = aliases.get(source_id, source_id)
    if candidate in registered_adapter_ids():
        return candidate, True
    if source.get("source_type") in {"file", "manual"}:
        return "local_file", True
    return "generic_http", True


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    required = ["source_registry_config", "api_source_definitions", "manual_source_definitions"]
    missing = [name for name in required if name not in inputs]
    if missing:
        raise ContractValidationError(f"missing required inputs: {missing}")
    reject_forbidden_fields(inputs)
    reject_materialized_secrets(inputs)

    registry_config = inputs["source_registry_config"]
    if not isinstance(registry_config, dict):
        raise ContractValidationError("source_registry_config must be an object")

    defaults = registry_config.get("defaults") if isinstance(registry_config.get("defaults"), dict) else {}
    sources = [*_records(inputs["api_source_definitions"], "api_source"), *_records(inputs["manual_source_definitions"], "manual_source")]
    seen = set()
    normalized = []
    for raw_source in sources:
        if not isinstance(raw_source, dict):
            raise ContractValidationError("source definition must be an object")
        source = deepcopy(raw_source)
        reject_forbidden_fields(source)
        reject_materialized_secrets(source)
        raw_source_id = source.get("source_id")
        source_type = source.get("source_type")
        source_id = str(raw_source_id).strip() if raw_source_id is not None else ""
        source_key = source_id.casefold()
        if not source_id or source_key in seen:
            raise ContractValidationError("source_id must be present and unique after canonical normalization")
        if source_type not in SOURCE_TYPES:
            raise ContractValidationError(f"source_type not allowed: {source_type}")
        seen.add(source_key)
        source["source_id"] = source_id

        adapter_id, adapter_registered = _default_adapter_id(source, strict_adapter_ids=bool(config.get("strict_adapter_ids")))
        credential_kind = str(source.get("credential_kind") or defaults.get("credential_kind") or "NONE").upper()
        if credential_kind not in CREDENTIAL_KINDS:
            raise ContractValidationError(f"credential_kind not allowed: {credential_kind}")
        credential_handle = source.get("credential_handle")
        validate_credential_handle_values(credential_handle)
        validate_credential_handle_values(source.get("credential_handles"))
        if credential_kind != "NONE" and not credential_handle and not source.get("credential_handles"):
            # Allow declaration now and enforce at execution only in non-strict compatibility mode.
            if config.get("strict_credentials"):
                raise ContractValidationError(f"credential_handle required for {source_id}")

        datasets = normalize_dataset_entries(source)
        normalized_datasets = []
        for dataset in datasets:
            domain, inferred = normalize_domain(
                dataset.get("domain") or source.get("source_category") or source.get("domain"),
                source_type=source_type,
            )
            entry = dict(dataset)
            entry["domain"] = domain
            entry["routing_inferred"] = bool(inferred)
            entry.setdefault("authority_role", source.get("authority_role") or "primary")
            normalized_datasets.append(entry)

        clean = deep_copy_without_secret_material(source)
        clean["source_id"] = source_id
        clean["source_type"] = source_type
        clean["provider"] = str(source.get("provider") or source_id)
        clean["adapter_id"] = adapter_id
        clean["adapter_registered"] = bool(adapter_registered)
        clean["adapter_resolution"] = "REGISTERED" if adapter_registered else "UNREGISTERED_EXPLICIT"
        clean["credential_kind"] = credential_kind
        clean["credential_handle"] = credential_handle
        if source.get("credential_handles"):
            clean["credential_handles"] = dict(source["credential_handles"])
        clean["enabled"] = bool(source.get("enabled", True))
        clean["datasets"] = normalized_datasets
        clean.setdefault("rate_policy_id", source.get("rate_policy_id") or defaults.get("rate_policy_id"))
        clean.setdefault("retention_policy_id", source.get("retention_policy_id") or defaults.get("retention_policy_id"))
        normalized.append(clean)

    normalized.sort(key=lambda item: item["source_id"])
    semantic = {
        "registry_id": registry_config.get("registry_id"),
        "sources": normalized,
        "policies": registry_config.get("policies", {}),
    }
    digest = stable_digest(semantic)
    return {
        "module_id": "P1.S1.M01",
        "module_name": "source_registry_loader",
        "phase": "phase_01_ingestion",
        "subphase": "P1.S1",
        "contract": "P1_S1_M01_source_registry_loader.yaml",
        "required_inputs": required,
        "outputs": {"source_registry": {
            "artifact_id": f"source_registry-{digest[:12]}",
            "created_at": config.get("created_at", "2024-01-01T00:00:00Z"),
            "lineage_id": f"lineage-source_registry-{digest[:12]}",
            "pipeline_version": config.get("pipeline_version", "V14.1-RC4.1"),
            "schema_version": "2",
            "registry_content_hash": digest,
            "sources": normalized,
        }},
    }
