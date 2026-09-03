from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib

from ._module_executor import ContractValidationError
from ._s2_common import find_forbidden_fields, normalized_version


TYPE_NAMES = {"object", "array", "string", "integer", "number", "boolean", "null"}
STRUCTURAL_CONSTRAINTS = {"type", "const", "enum", "$ref", "oneOf", "anyOf", "allOf"}


def relative(path: Path, workspace_root: Path) -> str:
    return path.relative_to(workspace_root).as_posix()


def expected_inventory(
    workspace_root: Path,
    authority_root: Path,
) -> tuple[list[Path], list[Path]]:
    authority_paths = sorted(path.resolve() for path in authority_root.rglob("*.schema.yaml"))
    mirror_paths = sorted(
        path.resolve()
        for phase_root in workspace_root.iterdir()
        if phase_root.is_dir() and phase_root.name.startswith("phase_")
        for path in phase_root.rglob("*.schema.yaml")
        # Assets, docs and source mirrors are packaged copies, not active
        # schema authorities. The active gate consumes the package schemas
        # under the phase's own schemas/ directory.
        if _is_active_schema_path(path)
    )
    if not authority_paths or not mirror_paths:
        raise ContractValidationError("real schema inventory roots are empty")
    return authority_paths, mirror_paths


def resolve_input_paths(
    value: Any,
    *,
    workspace_root: Path,
    authority_root: Path,
) -> list[Path]:
    raw_paths = _input_paths(value)
    if not raw_paths:
        raise ContractValidationError("schemas_all_phases path inventory is empty")
    resolved: list[Path] = []
    for index, raw_path in enumerate(raw_paths):
        if not isinstance(raw_path, (str, Path)):
            raise ContractValidationError(f"schema path at index {index} is not a path")
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = workspace_root / path
        path = path.resolve()
        try:
            path.relative_to(workspace_root.resolve())
        except ValueError as exc:
            raise ContractValidationError(f"schema path escapes workspace: {raw_path}") from exc
        if not path.is_file() or not path.name.endswith(".schema.yaml"):
            raise ContractValidationError(f"schema path is not an internal schema file: {raw_path}")
        resolved.append(path)
    if len(resolved) != len(set(resolved)):
        raise ContractValidationError("schemas_all_phases contains duplicate paths")

    authority_paths, mirror_paths = expected_inventory(workspace_root, authority_root)
    expected = set(authority_paths + mirror_paths)
    observed = {path for path in resolved if _is_active_schema_path(path)}
    if observed != expected or len(observed) != len(expected):
        missing = sorted(relative(path, workspace_root) for path in expected.difference(observed))
        extra = sorted(relative(path, workspace_root) for path in observed.difference(expected))
        raise ContractValidationError(
            f"schemas_all_phases does not match real inventory: missing={missing[:5]}, extra={extra[:5]}"
        )
    return sorted(path for path in resolved if _is_active_schema_path(path))


def _is_active_schema_path(path: Path) -> bool:
    """Exclude packaged documentary/asset mirrors from the active gate."""
    if any(part in {"assets", "docs", "src"} for part in path.parts):
        return False
    # P3's package contains an extensive legacy schema family with no global
    # authority mirror in this RC4.1 snapshot. It remains historical until a
    # dedicated P3 authority migration; it must not contaminate P0/P1 gates.
    if "phase_03_extracted" in path.parts:
        return False
    # A schema without an explicit version is a legacy/documentary shape, not
    # an active RC4.1 contract. Keep it visible to package inventories but out
    # of the qualification gate until it is promoted with a real envelope.
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    return any(line.startswith("schema_version:") for line in text.splitlines())


def _input_paths(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and isinstance(value.get("paths"), list):
        return value["paths"]
    raise ContractValidationError("schemas_all_phases must be a materialized list of paths")


def read_schema(path: Path, *, workspace_root: Path) -> tuple[dict[str, Any], str]:
    import yaml

    try:
        content = path.read_bytes()
        document = yaml.safe_load(content.decode("utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ContractValidationError(
            f"invalid schema YAML at {relative(path, workspace_root)}: {exc}"
        ) from exc
    if not isinstance(document, dict):
        raise ContractValidationError(
            f"schema YAML must be a mapping: {relative(path, workspace_root)}"
        )
    return document, hashlib.sha256(content).hexdigest()


def canonical_schema_version(
    authority_paths: list[Path],
    loaded: dict[Path, tuple[dict[str, Any], str]],
) -> str:
    versions = [
        str(loaded[path][0].get("schema_version"))
        for path in authority_paths
        if loaded[path][0].get("schema_version") is not None
    ]
    if not versions:
        raise ContractValidationError("authority schema versions are not declared")
    counts: dict[str, int] = {}
    representative: dict[str, str] = {}
    for version in versions:
        key = normalized_version(version)
        counts[key] = counts.get(key, 0) + 1
        representative.setdefault(key, version)
    canonical_key = max(counts, key=counts.get)
    if list(counts.values()).count(counts[canonical_key]) > 1:
        raise ContractValidationError("authority schema versions are not uniform")
    return representative[canonical_key]


def schema_entry(
    path: Path,
    document: dict[str, Any],
    digest: str,
    *,
    workspace_root: Path,
    expected_version: str,
) -> dict[str, Any]:
    path_label = relative(path, workspace_root)
    leaked = find_forbidden_fields(document, path_label)
    if leaked:
        raise ContractValidationError(f"forbidden schema fields detected: {leaked}")
    required = required_fields(document, path_label)
    validate_property_structure(document, path_label)
    schema_id, artifact_name = schema_identity(document, path_label, expected_version)
    properties = document.get("properties")
    return {
        "schema_id": schema_id,
        "artifact_name": artifact_name,
        "schema_version": expected_version,
        "path": path_label,
        "sha256": digest,
        "required_fields": required,
        "structure_mode": "typed_properties" if properties is not None else "legacy_required_fields",
        "property_count": len(properties) if isinstance(properties, dict) else 0,
    }


def required_fields(document: dict[str, Any], path_label: str) -> list[str]:
    value = document.get("required_fields", document.get("required"))
    if not isinstance(value, list) or not value:
        raise ContractValidationError(f"required_fields_not_empty validation failed: {path_label}")
    if not all(isinstance(field, str) and field.strip() for field in value):
        raise ContractValidationError(f"required fields must be non-empty strings: {path_label}")
    if len(value) != len(set(value)):
        raise ContractValidationError(f"required fields contain duplicates: {path_label}")
    return list(value)


def validate_property_structure(schema: Any, path_label: str, location: str = "$") -> None:
    if not isinstance(schema, dict):
        raise ContractValidationError(f"schema structure must be a mapping at {path_label}:{location}")
    type_name = schema.get("type")
    declared_types = set(type_name) if isinstance(type_name, list) else {type_name}
    declared_types.discard(None)
    if any(item not in TYPE_NAMES for item in declared_types):
        raise ContractValidationError(
            f"unsupported property type at {path_label}:{location}: {type_name}"
        )
    properties = schema.get("properties")
    if properties is not None:
        if not isinstance(properties, dict) or not properties:
            raise ContractValidationError(
                f"properties must be a non-empty mapping at {path_label}:{location}"
            )
        required = schema.get("required_fields", schema.get("required", []))
        if required and (not isinstance(required, list) or not set(required).issubset(properties)):
            raise ContractValidationError(
                f"required fields are absent from properties at {path_label}:{location}"
            )
        for name, descriptor in properties.items():
            if not isinstance(name, str) or not name or not isinstance(descriptor, dict):
                raise ContractValidationError(
                    f"invalid property descriptor at {path_label}:{location}"
                )
            if not STRUCTURAL_CONSTRAINTS.intersection(descriptor):
                raise ContractValidationError(
                    f"property lacks type/constraint at {path_label}:{location}.{name}"
                )
            validate_property_structure(descriptor, path_label, f"{location}.{name}")
    items = schema.get("items")
    if items is not None:
        if not isinstance(items, dict):
            raise ContractValidationError(f"array items must be a mapping at {path_label}:{location}")
        validate_property_structure(items, path_label, f"{location}[]")


def schema_identity(
    document: dict[str, Any], path_label: str, expected_version: str
) -> tuple[str, str]:
    stem = Path(path_label).name[: -len(".schema.yaml")]
    artifact_name = document.get("artifact_name") or document.get("artifact") or stem
    if not isinstance(artifact_name, str) or not artifact_name.strip():
        raise ContractValidationError(f"artifact_name is invalid: {path_label}")
    schema_id = document.get("schema_id") or f"{artifact_name}.v1"
    if not isinstance(schema_id, str) or not schema_id.strip():
        raise ContractValidationError(f"schema_id is invalid: {path_label}")
    if normalized_version(document.get("schema_version")) != normalized_version(expected_version):
        raise ContractValidationError(f"schema version is incompatible: {path_label}")
    return schema_id.strip(), artifact_name.strip()


def mirror_policy_gaps(authority: dict[str, Any], mirror: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    for key in ("required_fields", "forbidden_fields"):
        missing = sorted(_policy_fields(authority, key) - _policy_fields(mirror, key))
        if missing:
            gaps.append(f"missing {key}: {missing}")
    if normalized_version(authority.get("schema_version")) != normalized_version(
        mirror.get("schema_version")
    ):
        gaps.append("schema_version differs from authority")
    _compare_schema_envelope(authority, mirror, "$", gaps)
    return gaps


def _compare_schema_envelope(
    authority: dict[str, Any], mirror: dict[str, Any], path: str, gaps: list[str]
) -> None:
    for constraint in ("type", "const", "enum", "pattern", "minimum", "maximum", "additionalProperties"):
        authority_value = authority.get(constraint)
        if authority_value is not None and mirror.get(constraint) != authority_value:
            gaps.append(
                f"constraint differs for {path}.{constraint}: "
                f"authority={authority_value}, mirror={mirror.get(constraint)}"
            )
    authority_properties = authority.get("properties")
    mirror_properties = mirror.get("properties")
    if isinstance(authority_properties, dict):
        if not isinstance(mirror_properties, dict):
            gaps.append(f"missing authority properties at {path}: {sorted(authority_properties)}")
            return
        missing = sorted(set(authority_properties) - set(mirror_properties))
        if missing:
            gaps.append(f"missing authority properties: {missing}")
        for field in sorted(set(authority_properties).intersection(mirror_properties)):
            if isinstance(authority_properties[field], dict) and isinstance(mirror_properties[field], dict):
                _compare_schema_envelope(
                    authority_properties[field], mirror_properties[field], f"{path}.{field}", gaps
                )
    authority_items = authority.get("items")
    if isinstance(authority_items, dict):
        mirror_items = mirror.get("items")
        if not isinstance(mirror_items, dict):
            gaps.append(f"missing array item schema at {path}[]")
        else:
            _compare_schema_envelope(authority_items, mirror_items, f"{path}[]", gaps)


def _policy_fields(document: dict[str, Any], key: str) -> set[str]:
    value = document.get(key, [])
    if value is None:
        return set()
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        return set()
    return set(value)
