from __future__ import annotations

from functools import lru_cache
from typing import Any

from ._module_executor import ContractValidationError, PIPELINE_VERSION
from ._p0_s1_common import load_yaml_mapping, normalized_version, package_root


BASELINE_PATH = package_root() / "source_of_truth" / "architecture" / "ARCHITECTURE_BASELINE.yaml"


@lru_cache(maxsize=1)
def architecture_baseline() -> dict[str, Any]:
    baseline = load_yaml_mapping(BASELINE_PATH, "architecture baseline")
    required = {
        "baseline_id",
        "pipeline_version",
        "rc",
        "canonical_authorities",
        "registries",
        "planes",
        "matrix",
        "policy",
    }
    missing = sorted(required.difference(baseline))
    if missing:
        raise ContractValidationError(f"architecture baseline missing fields: {missing}")
    if normalized_version(baseline["pipeline_version"]) != normalized_version(PIPELINE_VERSION):
        raise ContractValidationError("architecture baseline pipeline version is incompatible")
    return baseline


def registry_baseline(kind: str) -> dict[str, Any]:
    registries = architecture_baseline().get("registries")
    if not isinstance(registries, dict) or not isinstance(registries.get(kind), dict):
        raise ContractValidationError(f"architecture baseline has no {kind} registry policy")
    return registries[kind]


def canonical_phases() -> list[dict[str, str]]:
    phases = registry_baseline("phase").get("phases")
    if not isinstance(phases, list) or not all(isinstance(item, dict) for item in phases):
        raise ContractValidationError("architecture baseline phase list is invalid")
    return [
        {
            "phase_id": str(item["phase_id"]),
            "package_name": str(item["package_name"]),
            "plane": str(item["plane"]),
        }
        for item in phases
    ]


def canonical_phase_ids() -> set[str]:
    return {item["phase_id"] for item in canonical_phases()}


def canonical_subphase_ids() -> set[str]:
    values = registry_baseline("subphase").get("subphase_ids")
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise ContractValidationError("architecture baseline subphase list is invalid")
    return set(values)


def expected_subphase_counts() -> dict[str, int]:
    counts = registry_baseline("subphase").get("phase_counts")
    if not isinstance(counts, dict):
        raise ContractValidationError("architecture baseline subphase counts are invalid")
    return {str(key): int(value) for key, value in counts.items()}



def canonical_module_ids() -> set[str]:
    values = registry_baseline("module").get("module_ids")
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise ContractValidationError("architecture baseline module list is invalid")
    return set(values)

def canonical_authorities() -> set[str]:
    values = architecture_baseline().get("canonical_authorities")
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise ContractValidationError("architecture baseline authorities are invalid")
    return {item.replace("\\", "/").rstrip("/") for item in values}


def forbidden_fields() -> set[str]:
    values = architecture_baseline().get("policy", {}).get("forbidden_fields")
    if not isinstance(values, list):
        raise ContractValidationError("architecture baseline forbidden fields are invalid")
    return {str(item) for item in values}


def economic_artifact_tokens() -> set[str]:
    values = architecture_baseline().get("policy", {}).get("economic_artifact_tokens")
    if not isinstance(values, list):
        raise ContractValidationError("architecture baseline economic tokens are invalid")
    return {str(item) for item in values}
