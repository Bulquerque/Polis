from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
import math
import re
from typing import Any, Iterable

from .errors import S4ContractError

IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")
SEMVER_RE = re.compile(r"^(?:v)?(\d+)\.(\d+)\.(\d+)$")
FORBIDDEN_FIELDS = frozenset({
    "future_return",
    "candidate_score",
    "rank_score",
    "portfolio_weight",
    "trade_decision",
    "buy_sell_signal",
    "realized_pnl",
})
SECRET_RE = re.compile(
    r"(^|_)(api_?key|secret|password|passwd|access_?token|"
    r"refresh_?token|authorization|cookie|private_?key)(_|$)",
    re.I,
)


def ensure_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise S4ContractError(
            "P3_S4_INPUT_NOT_MAPPING",
            f"{name} must be a mapping",
        )
    return deepcopy(value)


def ensure_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise S4ContractError(
            "P3_S4_INPUT_NOT_LIST",
            f"{name} must be a list",
        )
    return deepcopy(value)


def require_fields(
    value: dict[str, Any],
    fields: Iterable[str],
    *,
    location: str,
) -> None:
    missing = [
        field
        for field in fields
        if field not in value or value[field] is None
    ]
    if missing:
        raise S4ContractError(
            "P3_S4_REQUIRED_FIELD_MISSING",
            f"{location} missing {missing}",
        )


def require_identifier(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
        raise S4ContractError(
            "P3_S4_IDENTIFIER_INVALID",
            f"{field} must be lower_snake_case",
        )
    return value


def require_semver(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not SEMVER_RE.fullmatch(value):
        raise S4ContractError(
            "P3_S4_VERSION_INVALID",
            f"{field} must be MAJOR.MINOR.PATCH",
        )
    return value.removeprefix("v")


def require_non_empty_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise S4ContractError(
            "P3_S4_STRING_INVALID",
            f"{field} must be a non-empty string",
        )
    return value.strip()


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise S4ContractError(
                "P3_S4_NAIVE_DATETIME",
                "canonical values require timezone-aware datetimes",
            )
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def _reject_non_finite(value: Any, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise S4ContractError(
            "P3_S4_NON_FINITE_NUMBER",
            f"non-finite number at {path}",
        )
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_non_finite(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_non_finite(item, f"{path}[{index}]")


def canonical_bytes(value: Any) -> bytes:
    _reject_non_finite(value)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=_json_default,
    ).encode("utf-8")


def stable_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def content_hash(value: dict[str, Any]) -> str:
    core = {
        key: item
        for key, item in value.items()
        if key not in {"registry_hash", "policy_hash"}
    }
    return stable_sha256(core)


def find_paths(
    value: Any,
    predicate: Any,
    path: str = "$",
) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            current = f"{path}.{key}"
            if predicate(str(key)):
                found.append(current)
            found.extend(find_paths(item, predicate, current))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(find_paths(item, predicate, f"{path}[{index}]"))
    return found


def require_no_forbidden_fields(value: Any, name: str) -> None:
    paths = find_paths(value, lambda key: key in FORBIDDEN_FIELDS)
    if paths:
        raise S4ContractError(
            "P3_S4_FORBIDDEN_FIELD",
            f"{name} contains forbidden fields: {paths[:10]}",
        )


def require_no_secrets(value: Any, name: str) -> None:
    paths = find_paths(
        value,
        lambda key: bool(SECRET_RE.search(key))
        and not key.endswith("_handle"),
    )
    if paths:
        raise S4ContractError(
            "P3_S4_SECRET_DETECTED",
            f"{name} contains secret-like fields: {paths[:10]}",
        )


def require_unique(values: Iterable[str], *, field: str) -> None:
    observed = list(values)
    duplicates = sorted(
        value
        for value in set(observed)
        if observed.count(value) > 1
    )
    if duplicates:
        raise S4ContractError(
            "P3_S4_DUPLICATE_VALUE",
            f"{field} contains duplicates: {duplicates}",
        )


def schema_path_exists(schema: dict[str, Any], dotted_path: str) -> bool:
    current = schema
    for component in dotted_path.split("."):
        properties = current.get("properties")
        if not isinstance(properties, dict) or component not in properties:
            return False
        current = properties[component]
        if not isinstance(current, dict):
            return False
    return True
