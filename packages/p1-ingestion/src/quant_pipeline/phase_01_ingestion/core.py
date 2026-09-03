from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .modules._module_executor import ContractValidationError

FORBIDDEN_ECONOMIC_FIELDS = {
    "target", "future_return", "feature", "prediction", "score",
    "candidate_id", "portfolio_weight", "trade_decision", "realized_pnl",
}

MATERIALIZED_SECRET_KEYS = {
    "api_key", "secret", "password", "token", "client_secret", "authorization",
    "access_token", "refresh_token", "private_key",
}

SECRET_QUERY_KEYS = {
    "api_key", "apikey", "api-token", "api_token", "access_key", "token", "key",
    "registrationkey", "userid", "user_id", "client_secret", "password", "secret",
    "access_token", "refresh_token", "authorization",
}

TASK_STATES = {
    "PLANNED", "RUNNING", "SUCCESS", "FAILED_BLOCKING",
    "FAILED_NON_BLOCKING", "RATE_LIMITED", "QUOTA_EXHAUSTED", "UNAVAILABLE",
    "SKIPPED", "NOT_APPLICABLE",
}

CREDENTIAL_KINDS = {
    "NONE", "API_KEY", "KEY_SECRET_PAIR", "USER_ID", "IDENTIFICATION_HEADER", "TOKEN", "OAUTH2",
}

SOURCE_TYPES = {"api", "manual", "api_and_download", "download", "file"}

CONTRACT_MODES = {"LEGACY_V1", "CAPTURE_V2"}

_CREDENTIAL_HANDLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:/-]{1,127}$")

DOMAIN_ALIASES = {
    "market": "benchmark",
    "market_data": "benchmark",
    "underlying": "benchmark",
    "equity": "benchmark",
    "equities": "benchmark",
    "benchmark": "benchmark",
    "crypto": "crypto",
    "macro": "macro",
    "document": "document",
    "documents": "document",
    "news": "document",
    "regulatory": "document",
    "b3": "b3",
}


def stable_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json_default).encode("utf-8")
    return sha256(payload).hexdigest()


def _json_default(value: Any):
    if isinstance(value, bytes):
        return {"__bytes_sha256__": sha256(value).hexdigest(), "length": len(value)}
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)



VOLATILE_IDENTITY_FIELDS = {
    "requested_at", "retrieved_at", "ingested_at", "created_at",
    "execution_instance_id", "transport_elapsed_ms",
    "artifact_path", "raw_artifact_path", "source_file_path", "file_path",
    "path_exists", "artifact_root",
}


def semantic_identity_view(value: Any) -> Any:
    """Return a copy suitable for deterministic semantic IDs.

    Runtime observation timestamps remain in the artifacts, but they do not
    change content/snapshot/manifest identity during an otherwise identical replay.
    """
    if isinstance(value, dict):
        return {
            str(k): semantic_identity_view(v)
            for k, v in value.items()
            if str(k) not in VOLATILE_IDENTITY_FIELDS
        }
    if isinstance(value, (list, tuple)):
        return [semantic_identity_view(item) for item in value]
    return value


def identity_digest(value: Any) -> str:
    return stable_digest(semantic_identity_view(value))

def deterministic_id(prefix: str, *parts: Any, length: int = 20) -> str:
    return f"{prefix}-{stable_digest(parts)[:length]}"


def walk_mappings(value: Any, path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], str, Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            key_s = str(key)
            yield path, key_s, item
            yield from walk_mappings(item, path + (key_s,))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from walk_mappings(item, path + (str(index),))


def reject_forbidden_fields(value: Any) -> None:
    found = []
    for path, key, _item in walk_mappings(value):
        if key.lower() in FORBIDDEN_ECONOMIC_FIELDS:
            found.append(".".join((*path, key)))
    if found:
        raise ContractValidationError(f"forbidden input fields detected: {sorted(found)}")


def reject_materialized_secrets(value: Any) -> None:
    found = []
    for path, key, item in walk_mappings(value):
        if key.lower() in MATERIALIZED_SECRET_KEYS and item not in (None, "", False):
            found.append(".".join((*path, key)))
    if found:
        raise ContractValidationError(f"credential material must not be present: {sorted(found)}")


def ensure_no_source_placeholder(value: Any) -> None:
    for path, key, item in walk_mappings(value):
        if key == "source" and item not in (None, ""):
            raise ContractValidationError(
                f"source placeholder inputs are not accepted: {'.'.join((*path, key))}"
            )


def normalize_utc_timestamp(value: Any, *, field_name: str, allow_none: bool = True) -> str | None:
    if value in (None, ""):
        if allow_none:
            return None
        raise ContractValidationError(f"{field_name} is required")
    if not isinstance(value, str):
        raise ContractValidationError(f"{field_name} must be an ISO-8601 string")
    text = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise ContractValidationError(f"{field_name} must include explicit time and timezone")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractValidationError(f"{field_name} must be valid ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractValidationError(f"{field_name} must include an explicit timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def timestamp_le(left: str | None, right: str | None) -> bool | None:
    if left is None or right is None:
        return None
    ldt = datetime.fromisoformat(left.replace("Z", "+00:00"))
    rdt = datetime.fromisoformat(right.replace("Z", "+00:00"))
    return ldt <= rdt


def sanitize_url(url: str | None) -> str | None:
    if not url:
        return url
    try:
        split = urlsplit(url)
    except Exception:
        return url
    query = []
    for key, value in parse_qsl(split.query, keep_blank_values=True):
        query.append((key, "[REDACTED]" if key.lower() in SECRET_QUERY_KEYS else value))
    return urlunsplit((split.scheme, split.netloc, split.path, urlencode(query), split.fragment))


def deep_copy_without_secret_material(value: Any) -> Any:
    copied = deepcopy(value)
    _scrub(copied)
    return copied


def _scrub(value: Any) -> None:
    if isinstance(value, dict):
        for key in list(value):
            if str(key).lower() in MATERIALIZED_SECRET_KEYS:
                value[key] = "[REDACTED]"
            else:
                _scrub(value[key])
    elif isinstance(value, list):
        for item in value:
            _scrub(item)



def validate_timezone_name(value: Any) -> str:
    name = str(value or "UTC").strip()
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ContractValidationError(f"timezone must be a valid IANA timezone: {name}") from exc
    return name


def validate_credential_handle_values(value: Any) -> None:
    """Validate that credential handles look like references, not materialized secrets.

    This deliberately permits environment-style names and logical secret-manager paths,
    while rejecting whitespace-heavy/token-looking inline values.
    """
    if value in (None, {}):
        return
    handles = []
    if isinstance(value, str):
        handles = [value]
    elif isinstance(value, dict):
        handles = [item for item in value.values() if item not in (None, "")]
    elif isinstance(value, (list, tuple, set)):
        handles = [item for item in value if item not in (None, "")]
    else:
        raise ContractValidationError("credential handles must be strings, objects, or lists of strings")
    for handle in handles:
        if not isinstance(handle, str) or not _CREDENTIAL_HANDLE_RE.fullmatch(handle.strip()):
            raise ContractValidationError("credential handle must be a reference identifier, not credential material")


def normalize_contract_mode(value: Any) -> str:
    mode = str(value or "LEGACY_V1").upper()
    if mode not in CONTRACT_MODES:
        raise ContractValidationError(f"contract_mode not allowed: {mode}")
    return mode


def normalize_domain(value: Any, *, source_type: str | None = None) -> tuple[str, bool]:
    if isinstance(value, str) and value.strip():
        normalized = DOMAIN_ALIASES.get(value.strip().lower(), value.strip().lower())
        if normalized in {"b3", "macro", "benchmark", "crypto", "document"}:
            return normalized, False
    if source_type == "manual":
        return "document", True
    return "benchmark", True


def normalize_dataset_entries(source: dict) -> list[dict]:
    raw = source.get("datasets")
    if raw is None:
        legacy = source.get("dataset")
        if legacy is None:
            return [{"dataset_id": source.get("source_id"), "legacy_default": True}]
        raw = [legacy]
    if not isinstance(raw, list) or not raw:
        raise ContractValidationError("datasets must be a non-empty list when declared")
    entries = []
    seen = set()
    for item in raw:
        if isinstance(item, str):
            entry = {"dataset_id": item}
        elif isinstance(item, dict):
            entry = dict(item)
        else:
            raise ContractValidationError("dataset entry must be a string or object")
        dataset_id = entry.get("dataset_id") or entry.get("id") or entry.get("dataset")
        if not dataset_id:
            raise ContractValidationError("dataset_id is required")
        dataset_id = str(dataset_id)
        if dataset_id in seen:
            raise ContractValidationError("dataset_id must be unique within a source")
        seen.add(dataset_id)
        entry["dataset_id"] = dataset_id
        entries.append(entry)
    return entries
