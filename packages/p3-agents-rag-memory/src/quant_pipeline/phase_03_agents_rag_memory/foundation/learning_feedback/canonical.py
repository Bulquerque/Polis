from __future__ import annotations

from datetime import UTC, date, datetime
import hashlib
import json
import math
import re
from typing import Any, Iterable

from .errors import S3ContractError

FORBIDDEN_FIELDS = frozenset(
    {
        "future_return",
        "candidate_score",
        "rank_score",
        "portfolio_weight",
        "trade_decision",
        "buy_sell_signal",
        "direct_code_patch",
        "live_override",
        "current_backtest_mutation",
        "direct_model_change",
        "direct_ranking_change",
        "direct_portfolio_change",
        "realized_pnl",
    }
)

SECRET_RE = re.compile(
    r"(^|_)(api_?key|secret|password|passwd|access_?token|refresh_?token|"
    r"authorization|cookie|private_?key)(_|$)",
    re.IGNORECASE,
)


def ensure_mapping(value: Any, name: str) -> dict[str, Any]:
    """Return a mapping or reject the untrusted boundary value."""
    if not isinstance(value, dict):
        raise S3ContractError(
            "P3_S3_INPUT_NOT_MAPPING",
            f"{name} must be a mapping",
        )
    return value


def require_fields(
    value: dict[str, Any],
    fields: Iterable[str],
    *,
    location: str,
) -> None:
    """Require explicit fields; missing and null values are both invalid."""
    missing = [field for field in fields if value.get(field) is None]
    if missing:
        raise S3ContractError(
            "P3_S3_REQUIRED_FIELD_MISSING",
            f"{location} missing {missing}",
        )


def parse_aware_datetime(value: Any, *, field: str) -> datetime:
    """Parse an ISO-8601 datetime and normalize it to UTC."""
    if isinstance(value, datetime):
        observed = value
    elif isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            observed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise S3ContractError(
                "P3_S3_DATETIME_INVALID",
                f"{field} invalid: {value!r}",
            ) from exc
    else:
        raise S3ContractError(
            "P3_S3_DATETIME_INVALID",
            f"{field} must be ISO-8601",
        )

    if observed.tzinfo is None or observed.utcoffset() is None:
        raise S3ContractError(
            "P3_S3_NAIVE_DATETIME",
            f"{field} must include timezone",
        )
    return observed.astimezone(UTC)


def format_utc(value: datetime) -> str:
    """Serialize an aware datetime using the canonical UTC `Z` suffix."""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return format_utc(parse_aware_datetime(value, field="datetime"))
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def _reject_non_finite(value: Any, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise S3ContractError(
            "P3_S3_NON_FINITE_NUMBER",
            f"non-finite number at {path}",
        )
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_non_finite(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_non_finite(item, f"{path}[{index}]")


def canonical_bytes(value: Any) -> bytes:
    """Serialize data deterministically for hashing and replay."""
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
    """Return SHA-256 over the canonical byte representation."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def extract_records(value: dict[str, Any], name: str) -> list[dict[str, Any]]:
    """Extract the first supported record collection from an artifact."""
    for key in ("patches", "feedback_items", "records", "rows", "items"):
        rows = value.get(key)
        if isinstance(rows, list):
            if any(not isinstance(item, dict) for item in rows):
                raise S3ContractError(
                    "P3_S3_RECORD_NOT_MAPPING",
                    f"{name}.{key} contains non-mapping",
                )
            return [dict(item) for item in rows]
    return []


def forbidden_paths(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            current = f"{path}.{key}"
            if key in FORBIDDEN_FIELDS:
                found.append(current)
            found.extend(forbidden_paths(item, current))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(forbidden_paths(item, f"{path}[{index}]"))
    return found


def require_no_forbidden_fields(value: Any, name: str) -> None:
    found = forbidden_paths(value)
    if found:
        raise S3ContractError(
            "P3_S3_FORBIDDEN_FIELD",
            f"{name} contains forbidden fields: {found[:10]}",
        )


def secret_paths(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            current = f"{path}.{key}"
            if SECRET_RE.search(str(key)) and not str(key).endswith("_handle"):
                found.append(current)
            found.extend(secret_paths(item, current))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(secret_paths(item, f"{path}[{index}]"))
    return found


def require_no_secrets(value: Any, name: str) -> None:
    found = secret_paths(value)
    if found:
        raise S3ContractError(
            "P3_S3_SECRET_DETECTED",
            f"{name} contains secret fields: {found[:10]}",
        )


def parse_cycle_id(value: Any, *, field: str) -> int:
    """Accept integer cycle IDs or strings ending in a non-negative integer."""
    if isinstance(value, bool):
        raise S3ContractError("P3_S3_CYCLE_ID_INVALID", f"{field} invalid")
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, str):
        match = re.search(r"(\d+)$", value.strip())
        if match:
            return int(match.group(1))
    raise S3ContractError(
        "P3_S3_CYCLE_ID_INVALID",
        f"{field} must end in a non-negative integer",
    )


def parse_semver(value: str) -> tuple[int, int, int]:
    """Parse the deliberately supported SemVer core: MAJOR.MINOR.PATCH."""
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", value.strip())
    if not match:
        raise S3ContractError(
            "P3_S3_VERSION_INVALID",
            f"invalid semantic version: {value!r}",
        )
    return tuple(map(int, match.groups()))


def version_satisfies(version: str, expression: str) -> bool:
    """Evaluate exact versions or comma-separated comparator clauses."""
    current = parse_semver(version)
    expression = expression.strip()

    if re.fullmatch(r"v?\d+\.\d+\.\d+", expression):
        return current == parse_semver(expression)

    clauses = [clause.strip() for clause in expression.split(",") if clause.strip()]
    if not clauses:
        raise S3ContractError(
            "P3_S3_VERSION_RANGE_INVALID",
            "empty version range",
        )

    for clause in clauses:
        match = re.fullmatch(
            r"(>=|<=|>|<|==)?\s*(v?\d+\.\d+\.\d+)",
            clause,
        )
        if not match:
            raise S3ContractError(
                "P3_S3_VERSION_RANGE_INVALID",
                f"unsupported clause: {clause}",
            )
        operator = match.group(1) or "=="
        target = parse_semver(match.group(2))
        comparisons = {
            "==": current == target,
            ">=": current >= target,
            "<=": current <= target,
            ">": current > target,
            "<": current < target,
        }
        if not comparisons[operator]:
            return False
    return True


def lineage_token(value: dict[str, Any]) -> str | None:
    observed = value.get("handoff_lineage_id") or value.get("lineage_id")
    return str(observed) if observed not in (None, "") else None


def content_hash(output: dict[str, Any]) -> str:
    core = {key: value for key, value in output.items() if key != "content_hash"}
    return stable_sha256(core)
