from __future__ import annotations

from datetime import UTC, date, datetime
import hashlib
import json
import math
import re
from typing import Any, Iterable

from .errors import S2ContractError


FORBIDDEN_FIELDS = frozenset(
    {
        "target",
        "future_return",
        "label",
        "prediction",
        "candidate_id",
        "candidate_score",
        "rank_score",
        "portfolio_weight",
        "trade_decision",
        "realized_pnl",
        "buy_sell_signal",
    }
)

SECRET_KEY_PATTERN = re.compile(
    r"(^|_)(api_?key|secret|password|passwd|access_?token|refresh_?token|"
    r"authorization|cookie|private_?key)(_|$)",
    re.IGNORECASE,
)

RECORD_CONTAINER_KEYS = (
    "records",
    "rows",
    "items",
    "sources",
    "snapshots",
    "checks",
    "hints",
    "errors",
    "tasks",
)


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise TypeError("Naive datetime cannot be canonicalized")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"Unsupported canonical JSON value: {type(value).__name__}")


def compatibility_json_bytes(value: Any) -> bytes:
    """Match the P2/P3.S1 digest policy for referenced input verification."""

    return json.dumps(
        value,
        sort_keys=True,
        default=lambda item: item.isoformat() if isinstance(item, (datetime, date)) else str(item),
        ensure_ascii=True,
    ).encode("utf-8")


def compatibility_sha256(value: Any) -> str:
    return hashlib.sha256(compatibility_json_bytes(value)).hexdigest()


def _reject_non_finite(value: Any, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise S2ContractError(
            "P3_S2_NON_FINITE_NUMBER",
            f"Non-finite number is forbidden at {path}",
        )
    if isinstance(value, dict):
        for key, child in value.items():
            _reject_non_finite(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_non_finite(child, f"{path}[{index}]")


def snapshot_json_bytes(value: Any) -> bytes:
    """Deterministic compact JSON used by P3 snapshot/content hashes."""

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
    return hashlib.sha256(snapshot_json_bytes(value)).hexdigest()


def ensure_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise S2ContractError(
            "P3_S2_INPUT_NOT_MAPPING",
            f"{name} must be a mapping",
        )
    return value


def require_fields(
    value: dict[str, Any],
    fields: Iterable[str],
    *,
    location: str,
) -> None:
    missing = [field for field in fields if field not in value or value[field] is None]
    if missing:
        raise S2ContractError(
            "P3_S2_REQUIRED_FIELD_MISSING",
            f"{location} is missing required fields: {missing}",
        )


def extract_records(value: dict[str, Any], artifact_name: str) -> list[dict[str, Any]]:
    for key in RECORD_CONTAINER_KEYS:
        rows = value.get(key)
        if isinstance(rows, list):
            if any(not isinstance(row, dict) for row in rows):
                raise S2ContractError(
                    "P3_S2_RECORD_NOT_MAPPING",
                    f"{artifact_name}.{key} contains a non-mapping row",
                )
            return [dict(row) for row in rows]
    return [dict(value)]


def record_identity(row: dict[str, Any], index: int) -> str:
    for field in ("document_id", "event_id", "artifact_id", "record_id", "source_id"):
        observed = row.get(field)
        if observed not in (None, ""):
            return str(observed)
    return f"record-{index}"


def forbidden_paths(value: Any, *, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_FIELDS:
                found.append(child_path)
            found.extend(forbidden_paths(child, path=child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(forbidden_paths(child, path=f"{path}[{index}]"))
    return found


def require_no_forbidden_fields(value: Any, name: str) -> None:
    leaked = forbidden_paths(value)
    if leaked:
        raise S2ContractError(
            "P3_S2_FORBIDDEN_FIELD",
            f"{name} contains forbidden fields: {leaked[:10]}",
        )


def secret_paths(value: Any, *, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if SECRET_KEY_PATTERN.search(str(key)) and not str(key).endswith("_handle"):
                found.append(child_path)
            found.extend(secret_paths(child, path=child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(secret_paths(child, path=f"{path}[{index}]"))
    return found


def require_no_secrets(value: Any, name: str) -> None:
    leaked = secret_paths(value)
    if leaked:
        raise S2ContractError(
            "P3_S2_SECRET_DETECTED",
            f"{name} contains secret-bearing fields: {leaked[:10]}",
        )


def parse_aware_datetime(value: Any, *, field: str) -> datetime:
    if isinstance(value, datetime):
        observed = value
    elif isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            observed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise S2ContractError(
                "P3_S2_DATETIME_INVALID",
                f"{field} is not valid ISO-8601: {value!r}",
            ) from exc
    else:
        raise S2ContractError(
            "P3_S2_DATETIME_INVALID",
            f"{field} must be an ISO-8601 string or datetime",
        )
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise S2ContractError(
            "P3_S2_NAIVE_DATETIME",
            f"{field} must include a timezone offset",
        )
    return observed.astimezone(UTC)


def format_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def deep_sorted(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: deep_sorted(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        normalized = [deep_sorted(item) for item in value]
        if all(isinstance(item, dict) for item in normalized):
            identity_keys = (
                "artifact_name",
                "config_id",
                "schema_id",
                "provider_id",
                "interface_id",
                "model_id",
                "prompt_id",
            )
            for key in identity_keys:
                if all(key in item for item in normalized):
                    return sorted(normalized, key=lambda item: str(item[key]))
        return normalized
    return value
