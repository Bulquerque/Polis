from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
from typing import Any, Iterable

from .errors import S1ContractError


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
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize deterministically using the same policy as the P2 digest helper."""

    return json.dumps(
        value,
        sort_keys=True,
        default=_json_default,
        ensure_ascii=True,
    ).encode("utf-8")


def stable_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def normalize_version(value: str) -> str:
    return value.strip().lower().replace("_", "-")


def ensure_mapping(value: Any, artifact_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise S1ContractError(
            "P3_S1_INPUT_NOT_MAPPING",
            f"{artifact_name} must be a materialized mapping",
        )
    if value.get("source"):
        raise S1ContractError(
            "P3_S1_HIDDEN_SOURCE_REFERENCE",
            f"{artifact_name} cannot be synthesized from a source pointer",
        )
    return value


def extract_records(value: dict[str, Any], artifact_name: str) -> list[dict[str, Any]]:
    for key in RECORD_CONTAINER_KEYS:
        records = value.get(key)
        if isinstance(records, list):
            invalid = [index for index, row in enumerate(records) if not isinstance(row, dict)]
            if invalid:
                raise S1ContractError(
                    "P3_S1_RECORD_NOT_MAPPING",
                    f"{artifact_name}.{key} contains non-mapping rows at {invalid[:5]}",
                )
            return [dict(row) for row in records]
    raise S1ContractError(
        "P3_S1_RECORD_CONTAINER_MISSING",
        f"{artifact_name} must contain a records-compatible list",
    )


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


def require_no_forbidden_fields(value: Any, artifact_name: str) -> None:
    leaked = forbidden_paths(value)
    if leaked:
        raise S1ContractError(
            "P3_S1_FORBIDDEN_FIELD",
            f"{artifact_name} contains forbidden fields: {leaked[:10]}",
        )


def require_fields(
    value: dict[str, Any],
    fields: Iterable[str],
    *,
    location: str,
) -> None:
    missing = [field for field in fields if field not in value or value[field] is None]
    if missing:
        raise S1ContractError(
            "P3_S1_REQUIRED_FIELD_MISSING",
            f"{location} is missing required fields: {missing}",
        )


def record_identity(row: dict[str, Any], index: int) -> str:
    for field in ("document_id", "event_id", "artifact_id", "record_id", "source_id"):
        value = row.get(field)
        if value not in (None, ""):
            return str(value)
    return f"record-{index}"
