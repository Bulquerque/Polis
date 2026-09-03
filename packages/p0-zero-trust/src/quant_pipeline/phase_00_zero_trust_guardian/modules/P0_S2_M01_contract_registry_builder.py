from __future__ import annotations

from pathlib import Path
from typing import Any

from ._module_executor import ContractValidationError, PIPELINE_VERSION, SCHEMA_ROOT
from ._s2_common import (
    created_at,
    find_forbidden_fields,
    load_yaml_mapping_malformed,
    resolve_repo_path,
    stable_digest,
    validate_schema_value,
)
from ._s2_contract_registry import validate_global_contracts, validate_module_contracts


REPOSITORY_ROOT = Path(__file__).resolve().parents[6]
GLOBAL_PACKAGE_ROOT = (
    REPOSITORY_ROOT
    / "global_contracts_parallel_agents"
    / "v14_1_global_contracts_parallel_agents_RC4_1"
)
GLOBAL_CONTRACT_ROOT = GLOBAL_PACKAGE_ROOT / "contracts"
GLOBAL_SCHEMA_ROOT = GLOBAL_PACKAGE_ROOT / "schemas"
CANONICAL_MODULE_REGISTRY = GLOBAL_PACKAGE_ROOT / "source_of_truth" / "registries" / "module_registry.yaml"


def _load_yaml_mapping(path: Path, label: str) -> dict[str, Any]:
    """Compatibility alias retained for tests and downstream tooling."""
    return load_yaml_mapping_malformed(path, label)


def _find_forbidden_fields(value: Any, path: str = "inputs") -> list[str]:
    return find_forbidden_fields(value, path)


def _load_contract_manifest(value: Any) -> tuple[dict[str, Any], str]:
    if isinstance(value, dict) and isinstance(value.get("modules"), list):
        return value, "inline:contracts_all_phases"
    candidate: str | None = None
    if isinstance(value, (str, Path)):
        candidate = str(value)
    elif isinstance(value, dict) and isinstance(value.get("path"), str):
        candidate = value["path"]
    if not candidate:
        raise ContractValidationError(
            "contracts_all_phases must be the module registry mapping or an explicit YAML path"
        )
    path = Path(candidate).expanduser().resolve()
    manifest = _load_yaml_mapping(path, "contracts_all_phases")
    if not isinstance(manifest.get("modules"), list):
        raise ContractValidationError("contracts_all_phases must contain modules")
    return manifest, path.as_posix()


def _load_global_contract_paths(value: Any) -> tuple[list[Path], str]:
    candidate: str | None = None
    if isinstance(value, (str, Path)):
        candidate = str(value)
    elif isinstance(value, dict) and isinstance(value.get("path"), str):
        candidate = value["path"]
    if not candidate:
        raise ContractValidationError("global_contracts must be an explicit canonical directory path")
    directory = Path(candidate).expanduser().resolve()
    if directory != GLOBAL_CONTRACT_ROOT.resolve():
        raise ContractValidationError(f"global_contracts is not the canonical directory: {directory}")
    paths = sorted(directory.glob("*.yaml"), key=lambda path: path.name)
    if not paths:
        raise ContractValidationError("global_contracts canonical directory is empty")
    return paths, directory.as_posix()


def _resolve_internal_path(value: Any, label: str) -> tuple[Path, str]:
    return resolve_repo_path(
        value,
        label,
        REPOSITORY_ROOT,
        escape_message="escapes repository authority",
    )


def _schema_for_output(contract_file: Path, artifact: str) -> Path:
    """Resolve the current canonical naming binding without changing public contracts."""
    # Module contracts live under <package>/contracts/modules (and some
    # compatibility packages add another contracts nesting). Resolve from the
    # owning RC4.1 package root instead of assuming contracts/modules is flat.
    for parent in contract_file.parents:
        if parent.name.endswith("_agent_package_RC4_1"):
            schema_name = f"{artifact}.schema.yaml"
            root = parent / "schemas"
            direct = root / schema_name
            if direct.is_file():
                return direct
            matches = sorted(root.rglob(schema_name))
            if len(matches) == 1:
                return matches[0]
            if matches:
                # Foundation is the canonical namespace for P4 V14.9
                # handoff bundles; otherwise choose deterministic lexical path.
                foundation = [p for p in matches if p.parent.name == "foundation"]
                return sorted(foundation or matches)[0]
            return direct
    return contract_file.parents[1] / "schemas" / f"{artifact}.schema.yaml"


def _expected_registry_id() -> str:
    canonical = _load_yaml_mapping(CANONICAL_MODULE_REGISTRY, "canonical module registry")
    registry_id = canonical.get("registry_id")
    if not isinstance(registry_id, str) or not registry_id:
        raise ContractValidationError("canonical module registry has no registry_id")
    return registry_id


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config, required_inputs = _validated_runtime(inputs, config)
    manifest, contracts_source_path = _load_contract_manifest(inputs["contracts_all_phases"])
    if str(config.get("release_scope", "")).upper() == "P0_TECHNICAL_CLOSURE":
        manifest = {
            **manifest,
            "module_count": 40,
            "modules": [item for item in manifest["modules"] if item.get("phase_id") == "P0"],
        }
    global_paths, global_source_path = _load_global_contract_paths(inputs["global_contracts"])
    contracts = validate_module_contracts(
        manifest,
        repository_root=REPOSITORY_ROOT,
        resolve_internal_path=_resolve_internal_path,
        schema_for_output=_schema_for_output,
        expected_registry_id=_expected_registry_id(),
    )
    global_contracts = validate_global_contracts(
        global_paths,
        repository_root=REPOSITORY_ROOT,
        global_schema_root=GLOBAL_SCHEMA_ROOT,
    )
    artifact = _build_registry_artifact(
        contracts,
        global_contracts,
        contracts_source_path,
        global_source_path,
        config,
    )
    _validate_registry_artifact(artifact)
    return {
        "module_id": "P0.S2.M01",
        "module_name": "contract_registry_builder",
        "phase": "P0",
        "subphase": "P0.S2",
        "contract": "P0_S2_M01_contract_registry_builder.yaml",
        "required_inputs": required_inputs,
        "outputs": {"contract_registry": artifact},
    }


def _validated_runtime(
    inputs: dict, config: dict | None
) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(inputs, dict):
        raise ContractValidationError("inputs must be a dict")
    config = {} if config is None else config
    if not isinstance(config, dict):
        raise ContractValidationError("config must be a dict")
    required = ["contracts_all_phases", "global_contracts"]
    missing = [name for name in required if name not in inputs]
    if missing:
        raise ContractValidationError(f"missing required inputs: {missing}")
    leaked = _find_forbidden_fields(inputs)
    if leaked:
        raise ContractValidationError(f"forbidden input fields detected: {leaked}")
    return config, required


def _build_registry_artifact(
    contracts: list[dict[str, Any]],
    global_contracts: list[dict[str, Any]],
    contracts_source_path: str,
    global_source_path: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    digest = stable_digest({"contracts": contracts, "global_contracts": global_contracts})
    return {
        "artifact_id": f"contract-registry-{digest[:12]}",
        "created_at": created_at(config),
        "pipeline_version": PIPELINE_VERSION,
        "lineage_id": f"sha256:{digest}",
        "contracts_source_path": contracts_source_path,
        "global_contracts_source_path": global_source_path,
        "contract_count": len(contracts),
        "global_contract_count": len(global_contracts),
        "contracts": contracts,
        "global_contracts": global_contracts,
        "contract_has_source_target": True,
        "shared_artifacts_have_schema": True,
        "contract_identity_valid": True,
        "contract_hash_valid": True,
        "connection_graph_valid": True,
        "validation_evidence_status": "domain_oracle_pass_pending_independent_judge",
        "promotion_blocked": True,
    }


def _validate_registry_artifact(artifact: dict[str, Any]) -> None:
    schema = _load_yaml_mapping(
        SCHEMA_ROOT / "contract_registry.schema.yaml", "contract registry schema"
    )
    validate_schema_value(artifact, schema, "contract_registry")
    leaked = _find_forbidden_fields(artifact, "contract_registry")
    if leaked:
        raise ContractValidationError(f"forbidden output fields detected: {leaked}")
