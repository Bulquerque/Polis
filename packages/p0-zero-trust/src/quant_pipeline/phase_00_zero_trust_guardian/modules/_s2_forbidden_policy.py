from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import json
import re

import yaml

from ._module_executor import ContractValidationError, PIPELINE_VERSION
from ._s2_common import normalized_version


SCHEMA_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+(?:\.v[0-9]+|_v[0-9]+)$")
LINEAGE_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
PHASE_ID_PATTERN = re.compile(r"^P(?P<number>[0-9]+)$")
IGNORED_POLICY_KEYS = {
    "forbidden_fields",
    "allowed_fields",
    "allowed_weight_fields",
    "default_rule",
}
FIELD_IDENTITY_KEYS = {"name", "field", "field_name", "column", "column_name"}
FIELD_LIST_KEYS = {"required", "required_fields", "fields", "columns", "field_names"}
CONTEXT_KEYS = {"mode", "execution_mode", "usage", "lifecycle", "purpose", "runtime_mode"}
TRAINING_TOKENS = {"train", "training", "offline", "label", "evaluation", "backtest"}
INFERENCE_TOKENS = {"infer", "inference", "online", "serving", "production", "prediction"}


@dataclass(frozen=True)
class FieldPolicy:
    global_fields: frozenset[str]
    phase_forbidden: dict[str, frozenset[str]]
    phase_allowed: dict[str, frozenset[str]]
    source_path: str

    @property
    def all_fields(self) -> set[str]:
        result = set(self.global_fields)
        for fields in self.phase_forbidden.values():
            result.update(fields)
        return result


def load_mapping_input(
    value: Any,
    collection: str,
    label: str,
    *,
    workspace_root: Path,
) -> tuple[dict[str, Any], str]:
    if isinstance(value, dict) and isinstance(value.get(collection), list):
        return value, f"inline:{label}"
    candidate: str | None = None
    if isinstance(value, (str, Path)):
        candidate = str(value)
    elif isinstance(value, dict) and isinstance(value.get("path"), str):
        candidate = value["path"]
    if not candidate:
        raise ContractValidationError(f"{label} must be an inline mapping or explicit YAML path")
    path = Path(candidate).expanduser().resolve()
    try:
        path.relative_to(workspace_root.resolve())
    except ValueError as exc:
        raise ContractValidationError(f"{label} path is outside repository: {path}") from exc
    try:
        mapping = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ContractValidationError(f"invalid YAML for {label}: {path}: {exc}") from exc
    if not isinstance(mapping, dict) or not isinstance(mapping.get(collection), list):
        raise ContractValidationError(f"{label} must contain {collection}")
    return mapping, path.as_posix()


def load_policy(value: Any, *, workspace_root: Path) -> FieldPolicy:
    policy, source_path = load_mapping_input(
        value,
        "forbidden_fields",
        "forbidden_fields_yaml",
        workspace_root=workspace_root,
    )
    global_fields = _normalized_field_list(policy["forbidden_fields"], "forbidden_fields_yaml")
    if not {"target", "rank_score"}.issubset(global_fields):
        raise ContractValidationError("forbidden_fields_yaml must declare target and rank_score controls")
    phase_forbidden: dict[str, frozenset[str]] = {}
    phase_allowed: dict[str, frozenset[str]] = {}
    for path in sorted(workspace_root.glob("phase_*/*/contracts/FORBIDDEN_FIELDS.yaml")):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise ContractValidationError(f"invalid phase forbidden policy: {path}: {exc}") from exc
        if not isinstance(document, dict):
            continue
        phase_ids = phase_ids_from_path(path.as_posix())
        if len(phase_ids) != 1:
            continue
        phase_id = next(iter(phase_ids))
        fields = document.get("forbidden_fields", [])
        if isinstance(fields, list):
            phase_forbidden[phase_id] = frozenset(
                _normalized_field_list(fields, f"{phase_id} forbidden_fields")
            )
        allowed = set()
        for key in ("allowed_fields", "allowed_weight_fields"):
            raw = document.get(key, [])
            if isinstance(raw, list):
                allowed.update(
                    _normalized_field_list(raw, f"{phase_id} {key}", allow_empty=True)
                )
        phase_allowed[phase_id] = frozenset(allowed)
    return FieldPolicy(
        global_fields=frozenset(global_fields),
        phase_forbidden=phase_forbidden,
        phase_allowed=phase_allowed,
        source_path=source_path,
    )


def _normalized_field_list(
    value: Any, label: str, *, allow_empty: bool = False
) -> set[str]:
    if not isinstance(value, list) or (not allow_empty and not value) or not all(
        isinstance(field, str) and field.strip() for field in value
    ):
        raise ContractValidationError(f"{label} contains malformed fields")
    normalized = [field.lower() for field in value]
    if len(normalized) != len(set(normalized)):
        raise ContractValidationError(f"{label} contains duplicate fields")
    return set(normalized)


def contains_placeholder(value: Any) -> bool:
    if isinstance(value, dict):
        if set(value) == {"source"} and isinstance(value.get("source"), str):
            return True
        return any(contains_placeholder(child) for child in value.values())
    if isinstance(value, list):
        return any(contains_placeholder(child) for child in value)
    return False


def phase_ids_from_value(value: Any) -> set[str]:
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, list):
        raise ContractValidationError("phase IDs must be a string or list")
    phases: set[str] = set()
    for item in values:
        if not isinstance(item, str):
            raise ContractValidationError("phase IDs must be strings")
        match = PHASE_ID_PATTERN.fullmatch(item)
        if match is None or int(match.group("number")) > 9:
            raise ContractValidationError(f"invalid phase ID: {item}")
        phases.add(f"P{int(match.group('number'))}")
    return phases


def phase_ids_from_path(value: str) -> set[str]:
    phases = {
        f"P{int(number)}"
        for number in re.findall(r"(?:^|[/\\])phase_0*([0-9]+)(?:_|[/\\])", value)
        if int(number) <= 9
    }
    phases.update(
        f"P{int(number)}"
        for number in re.findall(r"(?:^|[^A-Za-z0-9])P([0-9]+)(?:[^A-Za-z0-9]|$)", value)
        if int(number) <= 9
    )
    return phases


def schema_phase_map(registry: dict[str, Any]) -> dict[str, set[str]]:
    phase_map: dict[str, set[str]] = {}
    mirrors = registry.get("mirrors", [])
    if not isinstance(mirrors, list):
        raise ContractValidationError("schema_registry.mirrors must be a list")
    for index, mirror in enumerate(mirrors):
        if not isinstance(mirror, dict):
            raise ContractValidationError(f"schema_registry mirror {index} must be a mapping")
        authority_path = mirror.get("authority_path")
        mirror_path = mirror.get("path")
        if not isinstance(authority_path, str) or not isinstance(mirror_path, str):
            raise ContractValidationError(f"schema_registry mirror {index} has invalid paths")
        phases = phase_ids_from_path(mirror_path)
        if not phases:
            raise ContractValidationError(f"schema_registry mirror {index} does not identify a phase")
        phase_map.setdefault(authority_path, set()).update(phases)
    return phase_map


def context_mode(entry: dict[str, Any], document: Any, source_id: str) -> str:
    explicit_tokens: set[str] = set()

    def collect_explicit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).lower() in CONTEXT_KEYS and isinstance(child, str):
                    explicit_tokens.update(re.findall(r"[a-z]+", child.lower()))
                collect_explicit(child)
        elif isinstance(value, list):
            for child in value:
                collect_explicit(child)

    collect_explicit(entry)
    collect_explicit(document)
    explicit_inference = explicit_tokens.intersection(INFERENCE_TOKENS)
    explicit_training = explicit_tokens.intersection(TRAINING_TOKENS)
    if explicit_inference and explicit_training:
        raise ContractValidationError(f"conflicting execution context for {source_id}")
    if explicit_inference:
        return "inference"
    if explicit_training:
        return "training"

    fallback = set(re.findall(r"[a-z]+", source_id.lower()))
    if fallback.intersection(INFERENCE_TOKENS):
        return "inference"
    if fallback.intersection(TRAINING_TOKENS):
        return "training"
    return "inference"


def field_occurrences(document: Any, policy_fields: set[str]) -> list[tuple[str, str]]:
    occurrences: set[tuple[str, str]] = set()

    def visit(value: Any, path: str, parent_key: str | None = None) -> None:
        if isinstance(value, dict):
            for raw_key, child in value.items():
                key = str(raw_key)
                normalized_key = key.lower()
                child_path = f"{path}.{key}"
                if normalized_key in IGNORED_POLICY_KEYS:
                    if isinstance(child, list) and all(isinstance(item, str) for item in child):
                        continue
                    visit(child, child_path, normalized_key)
                    continue
                if normalized_key in policy_fields:
                    occurrences.add((normalized_key, child_path))
                if normalized_key in FIELD_IDENTITY_KEYS and isinstance(child, str) and child.lower() in policy_fields:
                    occurrences.add((child.lower(), child_path))
                visit(child, child_path, normalized_key)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                child_path = f"{path}[{index}]"
                if parent_key in FIELD_LIST_KEYS and isinstance(child, str) and child.lower() in policy_fields:
                    occurrences.add((child.lower(), child_path))
                visit(child, child_path, parent_key)

    visit(document, "$")
    return sorted(occurrences)


def scan_sources(
    sources: list[dict[str, Any]], policy: FieldPolicy
) -> tuple[list[dict[str, Any]], int, int]:
    raw: list[dict[str, Any]] = []
    occurrence_count = 0
    allowed_count = 0
    for source in sources:
        fields = set(policy.global_fields)
        if source["source_kind"] == "artifact":
            for phase_id in source["phases"]:
                fields.update(policy.phase_forbidden.get(phase_id, frozenset()))
        occurrences = field_occurrences(source["document"], fields)
        occurrence_count += len(occurrences) * len(source["phases"])
        for field_name, location in occurrences:
            for phase_id in source["phases"]:
                code = violation_code(field_name, phase_id, source, policy)
                if code is None:
                    allowed_count += 1
                    continue
                raw.append(
                    {
                        "code": code,
                        "severity": "CRITICAL",
                        "field_name": field_name,
                        "phase_id": phase_id,
                        "source_kind": source["source_kind"],
                        "source_id": source["source_id"],
                        "schema_id": source["schema_id"],
                        "location": location,
                        "message": (
                            f"{field_name} violates Zero Trust field policy in "
                            f"{source['source_kind']} {source['source_id']} for {phase_id}"
                        ),
                        "release_blocking": True,
                    }
                )
    raw.sort(
        key=lambda item: (
            int(item["phase_id"][1:]),
            item["source_kind"],
            item["source_id"],
            item["location"],
            item["field_name"],
        )
    )
    return (
        [{"violation_id": f"FF-{index:04d}", **item} for index, item in enumerate(raw, 1)],
        occurrence_count,
        allowed_count,
    )


def violation_code(
    field_name: str,
    phase_id: str,
    source: dict[str, Any],
    policy: FieldPolicy,
) -> str | None:
    phase_number = int(phase_id[1:])
    if field_name in policy.phase_allowed.get(phase_id, frozenset()):
        return None
    if field_name == "target":
        return "TARGET_IN_INFERENCE" if source["mode"] == "inference" else None
    if field_name == "rank_score":
        return "RANK_SCORE_BEFORE_P7" if phase_number < 7 else None
    if field_name in policy.global_fields:
        return "FORBIDDEN_FIELD_PRESENT"
    if source["source_kind"] == "artifact" and field_name in policy.phase_forbidden.get(phase_id, frozenset()):
        return "FORBIDDEN_FIELD_PRESENT"
    return None


def source_digest(document: Any) -> str:
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()
