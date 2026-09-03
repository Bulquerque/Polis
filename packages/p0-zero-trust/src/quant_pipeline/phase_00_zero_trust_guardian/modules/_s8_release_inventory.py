from __future__ import annotations

from typing import Any

from ._p0_s8_utils import digest

_ID_KEYS = (
    "phase_id",
    "module_id",
    "contract_id",
    "schema_id",
    "artifact_name",
    "name",
    "id",
)
_COLLECTION_KEYS = {
    "phase": ("phases", "items", "registry"),
    "contract": ("contracts", "items", "registry", "modules"),
    "schema": ("schemas", "items", "registry"),
}


def build_release_inventory(
    phase_registry: dict[str, Any],
    contract_registry: dict[str, Any],
    schema_registry: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    return {
        "phases": _normalize_collection(phase_registry, "phase"),
        "contracts": _normalize_collection(contract_registry, "contract"),
        "schemas": _normalize_collection(schema_registry, "schema"),
    }


def compare_release_inventory(
    previous: dict[str, Any] | None,
    current: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(previous, dict):
        return _empty_summary(current), [], []
    summary: dict[str, Any] = {}
    blocking: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for kind in ("phases", "contracts", "schemas"):
        result, kind_blocking, kind_warnings = _compare_kind(
            kind,
            previous.get(kind),
            current.get(kind, []),
        )
        summary[kind] = result
        blocking.extend(kind_blocking)
        warnings.extend(kind_warnings)
    return summary, blocking, warnings


def _normalize_collection(data: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    raw = _find_collection(data, _COLLECTION_KEYS[kind])
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        identity = _identity(item, f"{kind}-{index:04d}")
        signature = _semantic_signature(item, kind)
        normalized.append(
            {
                "id": identity,
                "signature": signature,
                "digest": digest(signature),
            }
        )
    normalized.sort(key=lambda item: item["id"])
    return normalized


def _find_collection(data: dict[str, Any], keys: tuple[str, ...]) -> list[Any]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return [
                {"id": name, **item} if isinstance(item, dict) else {"id": name, "value": item}
                for name, item in value.items()
            ]
    return []


def _identity(item: dict[str, Any], fallback: str) -> str:
    for key in _ID_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return fallback


def _semantic_signature(item: dict[str, Any], kind: str) -> dict[str, Any]:
    if kind == "phase":
        keys = ("phase_id", "phase_name", "package", "package_name", "version")
    elif kind in {"contract", "contracts"}:
        keys = ("module_id", "contract_id", "inputs", "outputs", "required_inputs", "connections")
    else:
        keys = (
            "schema_id",
            "artifact_name",
            "schema_version",
            "required",
            "required_fields",
            "properties",
            "type",
        )
    signature = {key: item[key] for key in keys if key in item}
    return signature or {key: value for key, value in item.items() if key not in {"created_at", "lineage_id"}}


def _compare_kind(
    kind: str,
    previous_items: Any,
    current_items: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    previous_map = _index(previous_items)
    current_map = _index(current_items)
    added = sorted(set(current_map) - set(previous_map))
    removed = sorted(set(previous_map) - set(current_map))
    changed = sorted(
        identity
        for identity in set(previous_map) & set(current_map)
        if previous_map[identity].get("digest") != current_map[identity].get("digest")
    )
    blocking = [
        _finding("REMOVED_RELEASE_COMPONENT", kind, identity, "component removed from release baseline")
        for identity in removed
    ]
    warnings = [
        _finding("ADDED_RELEASE_COMPONENT", kind, identity, "component added to release baseline", "WARNING")
        for identity in added
    ]
    for identity in changed:
        classification = _classify_change(kind, previous_map[identity], current_map[identity])
        target = blocking if classification["release_blocking"] else warnings
        target.append(classification)
    result = {
        "previous_count": len(previous_map),
        "current_count": len(current_map),
        "added": added,
        "removed": removed,
        "changed": changed,
    }
    return result, blocking, warnings


def _index(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        return {}
    return {
        item["id"]: item
        for item in value
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def _classify_change(kind: str, previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    previous_signature = previous.get("signature", {})
    current_signature = current.get("signature", {})
    if kind in {"schema", "schemas"}:
        code, blocking = _classify_schema_change(previous_signature, current_signature)
    elif kind in {"contract", "contracts"}:
        code, blocking = _classify_contract_change(previous_signature, current_signature)
    else:
        code, blocking = "CHANGED_PHASE_DEFINITION", True
    return _finding(
        code,
        kind,
        str(current.get("id")),
        "release component changed relative to previous baseline",
        "BLOCKING" if blocking else "WARNING",
    )


def _classify_schema_change(previous: dict[str, Any], current: dict[str, Any]) -> tuple[str, bool]:
    previous_required = set(previous.get("required", previous.get("required_fields", [])) or [])
    current_required = set(current.get("required", current.get("required_fields", [])) or [])
    if current_required - previous_required:
        return "SCHEMA_REQUIRED_FIELD_ADDED", True
    previous_properties = previous.get("properties", {})
    current_properties = current.get("properties", {})
    if isinstance(previous_properties, dict) and isinstance(current_properties, dict):
        if set(previous_properties) - set(current_properties):
            return "SCHEMA_FIELD_REMOVED", True
        for field in set(previous_properties) & set(current_properties):
            if _field_type(previous_properties[field]) != _field_type(current_properties[field]):
                return "SCHEMA_FIELD_TYPE_CHANGED", True
    return "SCHEMA_COMPATIBLE_EXTENSION", False


def _classify_contract_change(previous: dict[str, Any], current: dict[str, Any]) -> tuple[str, bool]:
    old_inputs = set(previous.get("inputs", previous.get("required_inputs", [])) or [])
    new_inputs = set(current.get("inputs", current.get("required_inputs", [])) or [])
    old_outputs = set(previous.get("outputs", []) or [])
    new_outputs = set(current.get("outputs", []) or [])
    if new_inputs - old_inputs:
        return "CONTRACT_REQUIRED_INPUT_ADDED", True
    if old_outputs - new_outputs:
        return "CONTRACT_OUTPUT_REMOVED", True
    if old_inputs - new_inputs or new_outputs - old_outputs:
        return "CONTRACT_COMPATIBLE_EXTENSION", False
    return "CONTRACT_DEFINITION_CHANGED", True


def _field_type(value: Any) -> Any:
    return value.get("type") if isinstance(value, dict) else None


def _finding(code: str, kind: str, identity: str, detail: str, severity: str = "BLOCKING") -> dict[str, Any]:
    return {
        "code": code,
        "component_kind": kind,
        "component_id": identity,
        "detail": detail,
        "severity": severity,
        "release_blocking": severity == "BLOCKING",
    }


def _empty_summary(current: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    return {
        kind: {
            "previous_count": 0,
            "current_count": len(items),
            "added": [],
            "removed": [],
            "changed": [],
        }
        for kind, items in current.items()
    }
