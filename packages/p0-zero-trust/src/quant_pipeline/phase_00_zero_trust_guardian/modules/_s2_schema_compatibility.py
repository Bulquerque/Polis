from __future__ import annotations

from pathlib import Path
from typing import Any

from ._module_executor import ContractValidationError
from ._s2_common import load_yaml_mapping


def field_types(document: dict[str, Any], required_fields: list[str]) -> list[dict[str, str]]:
    properties = document.get("properties", {})
    result: list[dict[str, str]] = []
    for field in required_fields:
        descriptor = properties.get(field) if isinstance(properties, dict) else None
        declared = descriptor.get("type") if isinstance(descriptor, dict) else None
        if isinstance(declared, list):
            type_name = "|".join(str(item) for item in declared)
        elif isinstance(declared, str):
            type_name = declared
        else:
            type_name = "unspecified"
        result.append({"field_name": field, "type_name": type_name})
    return result


def semantic_schema_gaps(
    authority: dict[str, Any],
    producer: dict[str, Any],
    path: str = "$",
) -> list[str]:
    """Return contract-significant differences for fields governed by authority."""
    gaps: list[str] = []
    _compare_required(authority, producer, path, gaps)
    _compare_constraints(authority, producer, path, gaps)
    _compare_properties(authority, producer, path, gaps)
    _compare_items(authority, producer, path, gaps)
    return gaps


def _compare_required(
    authority: dict[str, Any], producer: dict[str, Any], path: str, gaps: list[str]
) -> None:
    required = authority.get("required_fields", authority.get("required", []))
    producer_required = producer.get("required_fields", producer.get("required", []))
    if isinstance(required, list) and required:
        if not isinstance(producer_required, list):
            gaps.append(f"{path}: producer does not declare required fields")
            return
        missing = sorted(set(required) - set(producer_required))
        if missing:
            gaps.append(f"{path}: producer drops required fields {missing}")


def _compare_constraints(
    authority: dict[str, Any], producer: dict[str, Any], path: str, gaps: list[str]
) -> None:
    for key in ("type", "const", "pattern", "minimum", "maximum", "additionalProperties"):
        expected = authority.get(key)
        if expected is not None and producer.get(key) != expected:
            gaps.append(
                f"{path}.{key}: authority={expected!r}, producer={producer.get(key)!r}"
            )
    authority_enum = authority.get("enum")
    producer_enum = producer.get("enum")
    if isinstance(authority_enum, list):
        if not isinstance(producer_enum, list):
            gaps.append(f"{path}.enum: producer removes authority enum")
        elif not set(producer_enum).issubset(set(authority_enum)):
            gaps.append(
                f"{path}.enum: producer can emit values outside authority {sorted(set(producer_enum)-set(authority_enum))}"
            )


def _compare_properties(
    authority: dict[str, Any], producer: dict[str, Any], path: str, gaps: list[str]
) -> None:
    authority_props = authority.get("properties")
    if not isinstance(authority_props, dict):
        return
    producer_props = producer.get("properties")
    if not isinstance(producer_props, dict):
        gaps.append(f"{path}: producer removes typed properties")
        return
    missing = sorted(set(authority_props) - set(producer_props))
    if missing:
        gaps.append(f"{path}: producer missing authority properties {missing}")
    for field in sorted(set(authority_props).intersection(producer_props)):
        authority_descriptor = authority_props[field]
        producer_descriptor = producer_props[field]
        if isinstance(authority_descriptor, dict) and isinstance(producer_descriptor, dict):
            gaps.extend(
                semantic_schema_gaps(
                    authority_descriptor,
                    producer_descriptor,
                    f"{path}.{field}",
                )
            )


def _compare_items(
    authority: dict[str, Any], producer: dict[str, Any], path: str, gaps: list[str]
) -> None:
    authority_items = authority.get("items")
    if not isinstance(authority_items, dict):
        return
    producer_items = producer.get("items")
    if not isinstance(producer_items, dict):
        gaps.append(f"{path}[]: producer removes item schema")
        return
    gaps.extend(semantic_schema_gaps(authority_items, producer_items, f"{path}[]"))


def load_schema_document(repository_root: Path, relative_path: str, label: str) -> dict[str, Any]:
    path = (repository_root / relative_path).resolve()
    try:
        path.relative_to(repository_root.resolve())
    except ValueError as exc:
        raise ContractValidationError(f"{label} is outside repository: {relative_path}") from exc
    return load_yaml_mapping(path, label)
