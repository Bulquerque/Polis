from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from ._module_executor import ContractValidationError
from ._option_identity import (
    normalize_expiration_date,
    normalize_option_type_label,
    resolve_canonical_contract_key,
)
from ._s3_market_helpers import (
    calendar_index,
    find_calendar_row,
    iso_date,
    parse_datetime,
    quality_state,
    reject_blocked_source,
    source_quality_index,
)

DOMAIN_OPTION_CONTRACT = "OPTION_CONTRACT"
DOMAIN_OPTION_QUOTE = "OPTION_QUOTE"
DOMAIN_UNKNOWN = "UNKNOWN"


def normalized_token(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "_").replace(" ", "_")


def explicit_option_domain(row: dict[str, Any]) -> str:
    value = row.get("record_domain") or row.get("domain") or row.get("dataset_type") or row.get("record_type")
    token = normalized_token(value)
    aliases = {
        "OPTION": DOMAIN_OPTION_CONTRACT,
        "OPTIONS": DOMAIN_OPTION_CONTRACT,
        "OPTION_CONTRACT": DOMAIN_OPTION_CONTRACT,
        "OPTION_CONTRACTS": DOMAIN_OPTION_CONTRACT,
        "OPTION_CHAIN": DOMAIN_OPTION_CONTRACT,
        "OPTION_QUOTE": DOMAIN_OPTION_QUOTE,
        "OPTION_QUOTES": DOMAIN_OPTION_QUOTE,
        "OPTIONS_QUOTE": DOMAIN_OPTION_QUOTE,
    }
    return aliases.get(token, DOMAIN_UNKNOWN)


def is_option_candidate(row: dict[str, Any]) -> bool:
    if explicit_option_domain(row) in {DOMAIN_OPTION_CONTRACT, DOMAIN_OPTION_QUOTE}:
        return True
    identity_markers = ("option_id", "expiration_date", "expiration", "strike", "option_type", "call_put")
    return any(row.get(field) not in (None, "") for field in identity_markers)


def is_quote_candidate(row: dict[str, Any]) -> bool:
    if explicit_option_domain(row) == DOMAIN_OPTION_QUOTE:
        return True
    if row.get("contract_key") not in (None, ""):
        return True
    quote_markers = ("bid", "ask", "last_price", "last", "open_interest", "financial_volume")
    return is_option_candidate(row) and any(field in row for field in quote_markers)


def normalize_option_type(value: Any) -> str:
    return normalize_option_type_label(value)

def normalize_decimal(value: Any, *, field: str, positive: bool = False, nonnegative: bool = False) -> tuple[float, str]:
    if value in (None, ""):
        raise ContractValidationError(f"{field} is required")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ContractValidationError(f"invalid {field}: {value}") from exc
    if positive and number <= 0:
        raise ContractValidationError(f"{field} must be positive")
    if nonnegative and number < 0:
        raise ContractValidationError(f"{field} must be non-negative")
    normalized = format(number.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    if normalized in {"", "-0"}:
        normalized = "0"
    return float(number), normalized


def optional_number(value: Any, *, field: str, positive: bool = False, nonnegative: bool = False) -> float | None:
    if value in (None, ""):
        return None
    number, _ = normalize_decimal(value, field=field, positive=positive, nonnegative=nonnegative)
    return number


def normalize_expiration(row: dict[str, Any]) -> str:
    value = row.get("expiration_date") or row.get("expiration") or row.get("expiry")
    return normalize_expiration_date(value)

def canonical_contract_key(row: dict[str, Any]) -> tuple[str, str, list[str]]:
    """Compatibility wrapper over the single shared P2 option identity authority."""
    return resolve_canonical_contract_key(row)

def contract_calendar_status(row: dict[str, Any], calendar_panel: Any) -> tuple[str, dict[str, Any] | None]:
    index = calendar_index(calendar_panel)
    if not index:
        return "UNKNOWN", None
    probe = dict(row)
    probe["date"] = normalize_expiration(row)
    found = find_calendar_row(probe, index)
    if not found:
        return "UNKNOWN", None
    flag = found.get("is_trading_day")
    if flag is True:
        return "TRADING_DAY", found
    if flag is False:
        return "NON_TRADING_DAY", found
    return "UNKNOWN", found


def choose_primary(rows: list[dict[str, Any]], source_priority: list[str] | None = None) -> dict[str, Any]:
    priority = {str(source): index for index, source in enumerate(source_priority or [])}

    def score(row: dict[str, Any]) -> tuple[int, int, str, str]:
        quality = normalized_token(row.get("source_quality_status"))
        quality_rank = {"PASS": 0, "WARN": 1, "UNKNOWN": 2}.get(quality, 3)
        source = str(row.get("source_id") or "")
        source_rank = priority.get(source, len(priority) + 1)
        return quality_rank, source_rank, source, str(row.get("option_id") or "")

    return sorted(rows, key=score)[0]


def contract_indexes(contracts: list[dict[str, Any]]) -> dict[str, Any]:
    # ``contract_key`` is the public/drop-in compatible identifier.
    # ``canonical_contract_key`` is the economic identity used to reconcile
    # contracts across provider-specific identifiers.  Both are valid lookup
    # aliases for the same normalized contract.
    by_key: dict[str, dict[str, Any]] = {}
    by_canonical_key: dict[str, dict[str, Any]] = {}
    by_source_option: dict[tuple[str, str], dict[str, Any]] = {}
    by_option_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in contracts:
        key = row.get("contract_key")
        canonical = row.get("canonical_contract_key")
        if key not in (None, ""):
            by_key[str(key)] = row
        if canonical not in (None, ""):
            by_canonical_key[str(canonical)] = row
            by_key.setdefault(str(canonical), row)
        option_id = row.get("option_id")
        source_id = row.get("source_id")
        if option_id not in (None, ""):
            by_option_id[str(option_id)].append(row)
            if source_id not in (None, ""):
                by_source_option[(str(source_id), str(option_id))] = row
    return {
        "by_key": by_key,
        "by_canonical_key": by_canonical_key,
        "by_source_option": by_source_option,
        "by_option_id": by_option_id,
    }


def resolve_quote_contract(row: dict[str, Any], indexes: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    direct = row.get("contract_key")
    if direct not in (None, "") and str(direct) in indexes["by_key"]:
        return indexes["by_key"][str(direct)], "DIRECT_KEY"

    upstream_canonical = row.get("canonical_contract_key")
    if upstream_canonical not in (None, "") and str(upstream_canonical) in indexes["by_canonical_key"]:
        return indexes["by_canonical_key"][str(upstream_canonical)], "UPSTREAM_CANONICAL_IDENTITY"

    if row.get("strike") not in (None, "") and (row.get("expiration_date") or row.get("expiration")) not in (None, ""):
        try:
            key, _, _ = canonical_contract_key(row)
        except ContractValidationError:
            key = None
        if key and key in indexes["by_canonical_key"]:
            return indexes["by_canonical_key"][key], "CANONICAL_IDENTITY"
        if key and key in indexes["by_key"]:
            return indexes["by_key"][key], "CANONICAL_ALIAS"

    option_id = row.get("option_id")
    source_id = row.get("source_id")
    if option_id not in (None, "") and source_id not in (None, ""):
        found = indexes["by_source_option"].get((str(source_id), str(option_id)))
        if found:
            return found, "PROVIDER_OPTION_ID"
    if option_id not in (None, ""):
        matches = indexes["by_option_id"].get(str(option_id), [])
        if len(matches) == 1:
            return matches[0], "UNIQUE_OPTION_ID"
        if len(matches) > 1:
            raise ContractValidationError(f"quote_contract_ambiguous: {option_id}")
    return None, "NOT_FOUND"


def combine_quality_status(reasons: list[str], source_status: str) -> str:
    # Absence of optional market fields is an information boundary, not a
    # quality failure.  The reasons remain attached to the row so consumers
    # know why execution/cost metrics are unavailable.
    informational = {"MISSING_BID", "MISSING_ASK", "MISSING_LAST_PRICE"}
    effective_reasons = [reason for reason in reasons if reason not in informational]
    if any(reason.startswith("CROSSED_MARKET") for reason in reasons):
        return "BLOCK"
    if source_status == "BLOCK":
        return "BLOCK"
    if effective_reasons or source_status == "WARN":
        return "WARN"
    return "PASS"


def quote_age_seconds(available_at: Any, as_of: Any) -> float | None:
    if available_at in (None, "") or as_of in (None, ""):
        return None
    try:
        available = parse_datetime(available_at, field="available_at")
        cutoff = parse_datetime(as_of, field="as_of_date")
    except ContractValidationError:
        return None
    return max(0.0, (cutoff - available).total_seconds())


def bounded_log_score(value: float | None) -> float | None:
    if value is None or value < 0:
        return None
    transformed = math.log1p(value)
    return transformed / (1.0 + transformed) if transformed > 0 else 0.0


def mean_known(values: list[float | None]) -> float | None:
    known = [float(value) for value in values if value is not None]
    if not known:
        return None
    return sum(known) / len(known)


def source_quality_for(row: dict[str, Any], panel: Any) -> tuple[str, list[str]]:
    index = source_quality_index(panel)
    return reject_blocked_source(row, index)


def source_quality_status(row: dict[str, Any], panel: Any) -> tuple[str, list[str]]:
    index = source_quality_index(panel)
    return quality_state(row.get("source_id"), index)
def option_source_allowed(row: dict[str, Any], config: dict) -> bool:
    """Apply an explicit option-source policy without affecting context sources."""
    allowed = config.get("allowed_option_providers")
    if not allowed:
        return True
    allowed_set = {str(value).strip().lower() for value in allowed if value not in (None, "")}
    source_values = {
        str(row.get(field)).strip().lower()
        for field in ("provider", "source_id", "source_category", "domain")
        if row.get(field) not in (None, "")
    }
    return bool(source_values & allowed_set)
