from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json
import re
from datetime import datetime, timezone

import yaml

from ._module_executor import ContractValidationError, PIPELINE_VERSION, SCHEMA_ROOT


MODULE_ID_PATTERN = re.compile(
    r"^P(?P<phase>[0-9]+)\.S(?P<subphase>[0-9]+)\.M(?P<module>[0-9]+)$"
)
LINEAGE_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def package_root() -> Path:
    """Resolve the phase package root without relying on a magic parent index."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "source_of_truth").is_dir() and (parent / "schemas").is_dir():
            return parent
    raise ContractValidationError("unable to resolve phase package root")


def workspace_root() -> Path:
    """Resolve the workspace root that contains all phase packages."""
    root = package_root()
    for parent in root.parents:
        if any(parent.glob("phase_01_ingestion")) and any(parent.glob("phase_09_extracted")):
            return parent
    # The isolated reform package intentionally remains usable without the full workspace.
    return root.parent


def load_yaml_mapping(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ContractValidationError(f"{label} does not exist: {path}")
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ContractValidationError(f"invalid YAML for {label}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractValidationError(f"invalid {label} mapping: {path}")
    return value


def load_mapping_input(
    value: Any,
    *,
    label: str,
    collection_key: str | None = None,
    symbolic_name: str | None = None,
) -> tuple[dict[str, Any], str]:
    if isinstance(value, dict) and "path" not in value:
        if collection_key is None or isinstance(value.get(collection_key), list):
            if symbolic_name and set(value) == {"source"}:
                raise ContractValidationError(
                    f"{symbolic_name} must be a materialized mapping or an explicit YAML path"
                )
            return value, f"inline:{symbolic_name or label.replace(' ', '_')}"

    candidate: str | None = None
    if isinstance(value, (str, Path)):
        candidate = str(value)
    elif isinstance(value, dict) and isinstance(value.get("path"), str):
        candidate = value["path"]
    if not candidate:
        subject = symbolic_name or label.replace(" ", "_")
        raise ContractValidationError(
            f"{subject} must be a mapping or an explicit YAML path"
        )

    path = Path(candidate).expanduser().resolve()
    mapping = load_yaml_mapping(path, label)
    if collection_key and not isinstance(mapping.get(collection_key), list):
        raise ContractValidationError(f"invalid {label} mapping: {path}")
    return mapping, path.as_posix()


def normalized_version(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def stable_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def created_at(config: dict[str, Any]) -> str:
    value = config.get("created_at") or config.get("generated_at") or config.get("evaluation_time")
    if value:
        return str(value)
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def require_inputs(inputs: Any, config: Any, required: list[str]) -> dict[str, Any]:
    if not isinstance(inputs, dict):
        raise ContractValidationError("inputs must be a dict")
    if config is None:
        config = {}
    if not isinstance(config, dict):
        raise ContractValidationError("config must be a dict")
    missing = [name for name in required if name not in inputs]
    if missing:
        raise ContractValidationError(f"missing required inputs: {missing}")
    return config


def find_forbidden_fields(
    value: Any,
    forbidden_fields: set[str],
    path: str = "inputs",
) -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key) in forbidden_fields:
                findings.append(child_path)
            findings.extend(find_forbidden_fields(child, forbidden_fields, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(
                find_forbidden_fields(child, forbidden_fields, f"{path}[{index}]")
            )
    return findings


def validate_schema_value(value: Any, schema: dict[str, Any], path: str) -> None:
    type_name = schema.get("type")
    checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
    }
    if type_name in checks and not checks[type_name](value):
        raise ContractValidationError(f"output schema type mismatch at {path}: {type_name}")
    if "const" in schema and value != schema["const"]:
        raise ContractValidationError(f"output schema const mismatch at {path}")
    if "enum" in schema and value not in schema["enum"]:
        raise ContractValidationError(f"output schema enum mismatch at {path}")
    _validate_scalar_limits(value, schema, path)
    _validate_collection(value, schema, path)


def _validate_scalar_limits(value: Any, schema: dict[str, Any], path: str) -> None:
    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)):
            raise ContractValidationError(f"output schema minLength mismatch at {path}")
        if schema.get("pattern") and re.fullmatch(str(schema["pattern"]), value) is None:
            raise ContractValidationError(f"output schema pattern mismatch at {path}")
    if isinstance(value, int) and not isinstance(value, bool):
        if "minimum" in schema and value < int(schema["minimum"]):
            raise ContractValidationError(f"output schema minimum mismatch at {path}")
        if "maximum" in schema and value > int(schema["maximum"]):
            raise ContractValidationError(f"output schema maximum mismatch at {path}")


def _validate_collection(value: Any, schema: dict[str, Any], path: str) -> None:
    if isinstance(value, list):
        if len(value) < int(schema.get("minItems", 0)):
            raise ContractValidationError(f"output schema minItems mismatch at {path}")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise ContractValidationError(f"output schema maxItems mismatch at {path}")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                validate_schema_value(item, item_schema, f"{path}[{index}]")
    elif isinstance(value, dict):
        required = schema.get("required_fields", schema.get("required", []))
        missing = [field for field in required if field not in value]
        if missing:
            raise ContractValidationError(f"output schema missing fields at {path}: {missing}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extras = sorted(set(value).difference(properties))
            if extras:
                raise ContractValidationError(f"output schema extra fields at {path}: {extras}")
        for key, child in value.items():
            child_schema = properties.get(key)
            if isinstance(child_schema, dict):
                validate_schema_value(child, child_schema, f"{path}.{key}")


def validate_output(
    artifact: dict[str, Any],
    *,
    schema_name: str,
    artifact_name: str,
    forbidden_fields: set[str],
) -> None:
    schema = load_yaml_mapping(SCHEMA_ROOT / schema_name, f"{artifact_name} schema")
    validate_schema_value(artifact, schema, artifact_name)
    leaked = find_forbidden_fields(artifact, forbidden_fields, artifact_name)
    if leaked:
        raise ContractValidationError(f"forbidden output fields detected: {leaked}")


def validate_lineage_id(value: Any, label: str) -> str:
    text = str(value or "")
    if LINEAGE_PATTERN.fullmatch(text) is None:
        raise ContractValidationError(f"{label} lineage_id is invalid")
    return text


def module_result(
    *,
    module_id: str,
    module_name: str,
    contract: str,
    required_inputs: list[str],
    output_name: str,
    artifact: dict[str, Any],
) -> dict[str, Any]:
    return {
        "module_id": module_id,
        "module_name": module_name,
        "phase": "P0",
        "subphase": "P0.S1",
        "contract": contract,
        "required_inputs": required_inputs,
        "outputs": {output_name: artifact},
    }


from ._canonical_schema_validator import validate_schema_value  # noqa: E402
