from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from typing import Any

from .canonical import (
    compatibility_sha256,
    deep_sorted,
    ensure_mapping,
    format_utc,
    parse_aware_datetime,
    require_no_forbidden_fields,
    require_no_secrets,
    stable_sha256,
)
from .errors import Issue, S2ContractError
from .models import ExecutionProfile, S2Settings, ValidationStatus
from .ports import ClockPort, ResourceResolverPort
from .schemas import SchemaRegistry
from .fingerprints import build_runtime_fingerprints
from ...shared.assets import source_or_packaged_root

LOGGER = logging.getLogger(__name__)


def _log_event(event: str, **fields: Any) -> None:
    LOGGER.info(event, extra={"event": event, **fields})


def _resource_resolver(config: dict[str, Any]) -> ResourceResolverPort:
    resolver = config.get("resource_resolver")
    if resolver is None or not callable(getattr(resolver, "resolve", None)):
        raise S2ContractError(
            "P3_S2_M02_RESOURCE_RESOLVER_MISSING",
            "An explicit ResourceResolverPort is required",
        )
    return resolver


def _processed_at(config: dict[str, Any]) -> datetime:
    raw = config.get("processed_at")
    if raw not in (None, ""):
        return parse_aware_datetime(raw, field="processed_at")
    clock = config.get("clock")
    if clock is None or not callable(getattr(clock, "now_utc", None)):
        raise S2ContractError(
            "P3_S2_M02_CLOCK_MISSING",
            "processed_at or an explicit ClockPort is required",
        )
    observed = clock.now_utc()
    if not isinstance(observed, datetime) or observed.tzinfo is None:
        raise S2ContractError(
            "P3_S2_M02_CLOCK_INVALID",
            "ClockPort.now_utc() must return an aware datetime",
        )
    return observed.astimezone(UTC)


def _resolve_configs(
    bindings_registry: dict[str, Any],
    resolver: ResourceResolverPort,
) -> list[dict[str, Any]]:
    bindings = bindings_registry.get("bindings")
    if not isinstance(bindings, dict) or not bindings:
        raise S2ContractError(
            "P3_S2_M02_CONFIG_BINDINGS_INVALID",
            "config_bindings_registry.bindings must be a non-empty mapping",
        )
    result: list[dict[str, Any]] = []
    for config_id, path in sorted(bindings.items()):
        if not isinstance(path, str) or not path:
            raise S2ContractError(
                "P3_S2_M02_CONFIG_PATH_INVALID",
                f"Invalid config path for {config_id}",
            )
        try:
            value = resolver.resolve(path)
        except Exception as exc:
            raise S2ContractError(
                "P3_S2_M02_CONFIG_RESOURCE_MISSING",
                f"Could not resolve config {config_id} at {path}",
            ) from exc
        require_no_forbidden_fields(value, f"config:{config_id}")
        require_no_secrets(value, f"config:{config_id}")
        result.append(
            {
                "config_id": str(config_id),
                "path": path,
                "content_hash": stable_sha256(value),
                "value_type": type(value).__name__,
            }
        )
    return result


def _resolve_schemas(
    inventory: dict[str, Any],
    resolver: ResourceResolverPort,
) -> list[dict[str, Any]]:
    rows = inventory.get("schemas")
    if not isinstance(rows, list) or not rows:
        raise S2ContractError(
            "P3_S2_M02_SCHEMA_INVENTORY_INVALID",
            "p3_schema_authority_inventory.schemas must be a non-empty list",
        )
    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise S2ContractError(
                "P3_S2_M02_SCHEMA_INVENTORY_INVALID",
                "Schema inventory entries must be mappings",
            )
        path = str(row.get("path", ""))
        schema_name = str(row.get("schema", ""))
        if not path or not schema_name:
            raise S2ContractError(
                "P3_S2_M02_SCHEMA_PATH_MISSING",
                "Schema inventory entry is missing schema/path",
            )
        try:
            value = resolver.resolve(path)
        except Exception as exc:
            raise S2ContractError(
                "P3_S2_M02_SCHEMA_RESOURCE_MISSING",
                f"Could not resolve schema {schema_name} at {path}",
            ) from exc
        require_no_secrets(value, f"schema:{schema_name}")
        result.append(
            {
                "schema_id": schema_name,
                "path": path,
                "class": str(row.get("class", "unknown")),
                "authority": str(row.get("authority", "unknown")),
                "content_hash": stable_sha256(value),
            }
        )
    if len({row["schema_id"] for row in result}) != len(result):
        raise S2ContractError(
            "P3_S2_M02_SCHEMA_ID_DUPLICATE",
            "Schema inventory contains duplicate schema IDs",
        )
    return sorted(result, key=lambda row: row["schema_id"])


def _provider_snapshot(registry: dict[str, Any]) -> tuple[list[dict[str, Any]], list[Issue]]:
    require_no_secrets(registry, "provider_adapter_registry_config")
    issues: list[Issue] = []
    providers: list[dict[str, Any]] = []
    explicit = registry.get("providers")
    if isinstance(explicit, list):
        for provider in explicit:
            if not isinstance(provider, dict):
                raise S2ContractError(
                    "P3_S2_M02_PROVIDER_ENTRY_INVALID",
                    "Provider entries must be mappings",
                )
            provider_id = str(provider.get("provider_id", ""))
            adapter_id = str(provider.get("adapter_id", ""))
            adapter_version = str(provider.get("adapter_version", ""))
            if not provider_id or not adapter_id:
                raise S2ContractError(
                    "P3_S2_M02_PROVIDER_ID_MISSING",
                    "provider_id and adapter_id are required",
                )
            if not adapter_version:
                issues.append(
                    Issue(
                        code="P3_S2_M02_ADAPTER_VERSION_MISSING",
                        severity="ERROR",
                        message="Provider adapter version is missing",
                        artifact_name="provider_adapter_registry_config",
                        record_id=provider_id,
                        field="adapter_version",
                    )
                )
            models = provider.get("models", [])
            if not isinstance(models, list):
                raise S2ContractError(
                    "P3_S2_M02_MODEL_INVENTORY_INVALID",
                    f"models must be a list for {provider_id}",
                )
            normalized_models: list[dict[str, Any]] = []
            for model in models:
                if not isinstance(model, dict):
                    raise S2ContractError(
                        "P3_S2_M02_MODEL_ENTRY_INVALID",
                        f"Model entry must be a mapping for {provider_id}",
                    )
                normalized_models.append(
                    {
                        "model_id": str(model.get("model_id", "UNKNOWN")),
                        "model_version": str(
                            model.get("model_version", model.get("revision", "UNKNOWN"))
                        ),
                        "release_date": model.get("release_date"),
                        "declared_knowledge_cutoff": model.get(
                            "declared_knowledge_cutoff", model.get("knowledge_cutoff")
                        ),
                        "training_data_cutoff": model.get(
                            "training_data_cutoff", model.get("training_cutoff")
                        ),
                        "canary_test_status": str(
                            model.get("canary_test_status", "NOT_RUN")
                        ),
                        "qualification_status": str(
                            model.get("qualification_status", "UNQUALIFIED")
                        ),
                        "evidence_refs": sorted(
                            str(item) for item in model.get("evidence_refs", [])
                        ),
                    }
                )
            providers.append(
                {
                    "provider_id": provider_id,
                    "adapter_id": adapter_id,
                    "adapter_version": adapter_version,
                    "capabilities": sorted(str(x) for x in provider.get("capabilities", [])),
                    "qualification_status": str(
                        provider.get("qualification_status", "UNQUALIFIED")
                    ),
                    "models": sorted(
                        normalized_models, key=lambda model: model["model_id"]
                    ),
                }
            )
    interfaces = registry.get("interfaces")
    if isinstance(interfaces, list):
        for interface in interfaces:
            if not isinstance(interface, dict):
                continue
            providers.append(
                {
                    "provider_id": f"interface:{interface.get('interface_id', 'unknown')}",
                    "adapter_id": str(interface.get("interface_id", "unknown")),
                    "adapter_version": str(interface.get("adapter_version", "")),
                    "capabilities": sorted(
                        str(x) for x in interface.get("required_capabilities", [])
                    ),
                    "qualification_status": "INTERFACE_ONLY",
                    "models": [],
                }
            )
    if not providers:
        issues.append(
            Issue(
                code="P3_S2_M02_PROVIDER_REGISTRY_EMPTY",
                severity="ERROR",
                message="No provider interfaces or concrete providers are declared",
                artifact_name="provider_adapter_registry_config",
            )
        )
    return sorted(providers, key=lambda row: row["provider_id"]), issues


@dataclass(frozen=True, slots=True)
class _SnapshotInputs:
    pit: dict[str, Any]
    handoff: dict[str, Any]
    bindings: dict[str, Any]
    providers: dict[str, Any]
    schema_inventory: dict[str, Any]


def _validated_snapshot_inputs(
    inputs: dict[str, Any],
    registry: SchemaRegistry,
) -> _SnapshotInputs:
    required = (
        "pit_validated_context",
        "phase3_handoff_manifest",
        "config_bindings_registry",
        "provider_adapter_registry_config",
        "p3_schema_authority_inventory",
    )
    missing = [name for name in required if name not in inputs]
    if missing:
        raise S2ContractError(
            "P3_S2_M02_REQUIRED_INPUT_MISSING",
            f"Missing inputs: {missing}",
        )
    values = _SnapshotInputs(
        pit=ensure_mapping(inputs[required[0]], required[0]),
        handoff=ensure_mapping(inputs[required[1]], required[1]),
        bindings=ensure_mapping(inputs[required[2]], required[2]),
        providers=ensure_mapping(inputs[required[3]], required[3]),
        schema_inventory=ensure_mapping(inputs[required[4]], required[4]),
    )
    registry.validate_internal("pit_validated_context", values.pit)
    registry.validate_external("phase3_handoff_manifest", values.handoff)
    for name, value in (
        ("pit_validated_context", values.pit),
        ("phase3_handoff_manifest", values.handoff),
        ("config_bindings_registry", values.bindings),
        ("provider_adapter_registry_config", values.providers),
        ("p3_schema_authority_inventory", values.schema_inventory),
    ):
        require_no_forbidden_fields(value, name)
        require_no_secrets(value, name)
    return values


def _seed_snapshot(config: dict[str, Any], issues: list[Issue]) -> dict[str, Any]:
    seed_manifest = config.get("seed_manifest")
    if seed_manifest is not None:
        seeds = deep_sorted(ensure_mapping(seed_manifest, "seed_manifest"))
        require_no_secrets(seeds, "seed_manifest")
        return seeds
    issues.append(
        Issue(
            code="P3_S2_M02_SEED_MANIFEST_MISSING",
            severity="ERROR",
            message="No execution seed manifest was supplied",
            artifact_name="phase3_run_snapshot",
            field="seed_manifest",
        )
    )
    return {
        "status": "MISSING",
        "global_seed": None,
        "component_seeds": {},
        "derivation_policy": None,
    }


def _prompt_snapshot(config: dict[str, Any]) -> list[dict[str, Any]]:
    raw_prompts = config.get("prompt_inventory", [])
    if not isinstance(raw_prompts, list):
        raise S2ContractError(
            "P3_S2_M02_PROMPT_INVENTORY_INVALID",
            "prompt_inventory must be a list",
        )
    prompts: list[dict[str, Any]] = []
    for prompt in raw_prompts:
        if not isinstance(prompt, dict):
            raise S2ContractError(
                "P3_S2_M02_PROMPT_ENTRY_INVALID",
                "prompt inventory entries must be mappings",
            )
        prompts.append(
            {
                "prompt_id": str(prompt.get("prompt_id", "")),
                "prompt_version": str(prompt.get("prompt_version", "")),
                "content_hash": str(prompt.get("content_hash", "")),
            }
        )
    prompts.sort(key=lambda row: (row["prompt_id"], row["prompt_version"]))
    require_no_secrets(prompts, "prompt_inventory")
    return prompts


def _budget_snapshot(config: dict[str, Any]) -> dict[str, Any]:
    raw = ensure_mapping(config.get("budget_manifest", {}), "budget_manifest")
    result = {"content_hash": stable_sha256(raw), "values": deep_sorted(raw)}
    require_no_secrets(result, "budget_manifest")
    return result


def _validate_qualification_metadata(
    settings: S2Settings,
    issues: list[Issue],
) -> None:
    if settings.execution_profile is not ExecutionProfile.QUALIFICATION:
        return
    blocking_codes = {
        "P3_S2_M02_ADAPTER_VERSION_MISSING",
        "P3_S2_M02_PROVIDER_REGISTRY_EMPTY",
        "P3_S2_M02_SEED_MANIFEST_MISSING",
    }
    blocking = [issue for issue in issues if issue.code in blocking_codes]
    if blocking:
        raise S2ContractError(
            "P3_S2_M02_QUALIFICATION_METADATA_INCOMPLETE",
            "Qualification snapshot metadata is incomplete",
            issues=blocking,
        )


def _run_id(config: dict[str, Any], handoff: dict[str, Any]) -> str:
    result = str(config.get("run_id") or handoff.get("handoff_id") or "")
    if not result:
        raise S2ContractError(
            "P3_S2_M02_RUN_ID_MISSING",
            "run_id or phase3_handoff_manifest.handoff_id is required",
        )
    return result


def _snapshot_core(
    *,
    values: _SnapshotInputs,
    settings: S2Settings,
    config: dict[str, Any],
    configs: list[dict[str, Any]],
    schemas: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    prompts: list[dict[str, Any]],
    seeds: dict[str, Any],
    budgets: dict[str, Any],
    runtime_fingerprints: dict[str, Any],
) -> dict[str, Any]:
    return deep_sorted(
        {
            "schema_version": "v14.1-rc4.1",
            "contract_version": "p3.s2.phase3_run_snapshot.v2",
            "identity": {
                "run_id": _run_id(config, values.handoff),
                "architecture_revision": str(config.get("architecture_revision", "P3-FINAL")),
                "pipeline_version": settings.pipeline_version,
                "execution_profile": settings.execution_profile.value,
                "execution_mode": str(config.get("execution_mode", "DEVELOPMENT")),
            },
            "temporal": dict(values.pit["run_temporal_boundary"]),
            "inputs": [
                {
                    "artifact_name": "pit_validated_context",
                    "content_hash": str(values.pit["content_hash"]),
                    "lineage_id": str(values.pit["lineage_id"]),
                },
                {
                    "artifact_name": "phase3_handoff_manifest",
                    "content_hash": compatibility_sha256(values.handoff),
                    "lineage_id": str(values.handoff.get("lineage_id", "")),
                },
            ],
            "configs": configs,
            "schemas": schemas,
            "providers": providers,
            "prompts": prompts,
            "seeds": seeds,
            "budgets": budgets,
            "runtime_fingerprints": runtime_fingerprints,
            "authority": {
                "config_bindings_version": str(values.bindings.get("version", "unknown")),
                "schema_registry_version": str(
                    values.schema_inventory.get("schema_registry_version", "unknown")
                ),
                "schema_count": len(schemas),
                "provider_registry_id": str(values.providers.get("registry_id", "unknown")),
            },
        }
    )


def _finalize_snapshot(
    *,
    core: dict[str, Any],
    issues: list[Issue],
    processed_at: datetime,
) -> dict[str, Any]:
    snapshot_hash = stable_sha256(core)
    snapshot_id = f"p3-snapshot-{snapshot_hash[:24]}"
    status = ValidationStatus.DEGRADED if issues else ValidationStatus.READY
    output: dict[str, Any] = {
        **core,
        "identity": {**core["identity"], "snapshot_id": snapshot_id},
        "validation_status": status.value,
        "issues": [issue.to_dict() for issue in issues],
        "snapshot_hash": snapshot_hash,
        "hash_profile": "p3_snapshot_canonical_sha256_v1",
        "created_at": format_utc(processed_at),
        "lineage_id": f"lineage-{snapshot_id}",
    }
    output["content_hash"] = stable_sha256(output)
    return output


def build_phase3_run_snapshot(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Freeze declared inputs, configs, schemas, adapters, seeds, and budgets."""

    config = config or {}
    settings = S2Settings.from_mapping(config)
    registry = SchemaRegistry()
    immutable_copy = deepcopy(inputs)
    _log_event("module_started", module_id="P3.S2.M02")

    values = _validated_snapshot_inputs(inputs, registry)
    resolver = _resource_resolver(config)
    configs = _resolve_configs(values.bindings, resolver)
    schemas = _resolve_schemas(values.schema_inventory, resolver)
    declared_count = int(values.schema_inventory.get("schema_count", len(schemas)))
    if declared_count != len(schemas):
        raise S2ContractError(
            "P3_S2_M02_SCHEMA_COUNT_MISMATCH",
            f"Schema inventory declares {declared_count} but resolves {len(schemas)}",
        )
    providers, issues = _provider_snapshot(values.providers)
    seeds = _seed_snapshot(config, issues)
    prompts = _prompt_snapshot(config)
    budgets = _budget_snapshot(config)
    runtime_fingerprints = build_runtime_fingerprints(source_or_packaged_root(), configs=configs, schemas=schemas, providers=providers, prompts=prompts, seeds=seeds, budgets=budgets)
    _validate_qualification_metadata(settings, issues)

    core = _snapshot_core(
        values=values,
        settings=settings,
        config=config,
        configs=configs,
        schemas=schemas,
        providers=providers,
        prompts=prompts,
        seeds=seeds,
        budgets=budgets,
        runtime_fingerprints=runtime_fingerprints,
    )
    output = _finalize_snapshot(
        core=core,
        issues=issues,
        processed_at=_processed_at(config),
    )
    if inputs != immutable_copy:
        raise S2ContractError(
            "P3_S2_INPUT_MUTATION_DETECTED",
            "P3.S2.M02 mutated its inputs",
        )
    registry.validate_internal("phase3_run_snapshot", output)
    require_no_forbidden_fields(output, "phase3_run_snapshot")
    require_no_secrets(output, "phase3_run_snapshot")
    _log_event(
        "module_succeeded",
        module_id="P3.S2.M02",
        validation_status=output["validation_status"],
        config_count=len(configs),
        schema_count=len(schemas),
        provider_count=len(providers),
        warning_count=len(issues),
    )
    return output
