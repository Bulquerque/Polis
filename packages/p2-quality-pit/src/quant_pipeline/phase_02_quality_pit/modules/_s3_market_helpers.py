from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from ._module_executor import ContractValidationError
from ._s2_temporal import parse_datetime_utc


DOMAIN_MACRO = "MACRO"
DOMAIN_BENCHMARK = "BENCHMARK"
DOMAIN_CALENDAR = "CALENDAR"
DOMAIN_CORPORATE_ACTION = "CORPORATE_ACTION"
DOMAIN_UNDERLYING = "UNDERLYING"
DOMAIN_UNKNOWN = "UNKNOWN"

_BLOCKING_QUALITY = {"BLOCK", "BLOCKED", "FAIL", "FAILED", "ERROR"}


def _normalized_token(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "_").replace(" ", "_")


def infer_domain(row: dict[str, Any]) -> str:
    """Classify a record conservatively.

    Explicit domain metadata wins. Legacy inference only fires when the row has
    fields strongly associated with one domain. Ambiguous rows stay UNKNOWN.
    """
    explicit = (
        row.get("record_domain")
        or row.get("domain")
        or row.get("dataset_type")
        or row.get("record_type")
    )
    token = _normalized_token(explicit)
    aliases = {
        "MACRO": DOMAIN_MACRO,
        "MACROECONOMIC": DOMAIN_MACRO,
        "BENCHMARK": DOMAIN_BENCHMARK,
        "INDEX": DOMAIN_BENCHMARK,
        "CALENDAR": DOMAIN_CALENDAR,
        "TRADING_CALENDAR": DOMAIN_CALENDAR,
        "CORPORATE_ACTION": DOMAIN_CORPORATE_ACTION,
        "CORPORATE_ACTIONS": DOMAIN_CORPORATE_ACTION,
        "UNDERLYING": DOMAIN_UNDERLYING,
        "EQUITY": DOMAIN_UNDERLYING,
        "MARKET": DOMAIN_UNDERLYING,
        "PRICE": DOMAIN_UNDERLYING,
    }
    if token in aliases:
        return aliases[token]

    if any(row.get(key) not in (None, "") for key in ("action_type", "ex_date", "record_date", "payment_date")):
        return DOMAIN_CORPORATE_ACTION
    if row.get("effective_date") not in (None, "") and row.get("adjustment_factor") not in (None, ""):
        return DOMAIN_CORPORATE_ACTION

    if any(row.get(key) not in (None, "") for key in ("calendar_id", "holiday_code", "session_open", "session_close", "early_close")):
        return DOMAIN_CALENDAR
    if "is_trading_day" in row and not any(key in row for key in ("open", "high", "low", "close", "price")):
        return DOMAIN_CALENDAR

    if row.get("benchmark_id") not in (None, ""):
        return DOMAIN_BENCHMARK
    if _normalized_token(row.get("asset_class")) in {"INDEX", "BENCHMARK"}:
        return DOMAIN_BENCHMARK

    macro_markers = ("series_id", "frequency", "reference_period", "observation_value", "vintage_date")
    if any(row.get(key) not in (None, "") for key in macro_markers):
        return DOMAIN_MACRO

    price_markers = ("open", "high", "low", "close", "price", "volume", "financial_volume")
    has_price = any(row.get(key) not in (None, "") for key in price_markers)
    has_option_identity = any(row.get(key) not in (None, "") for key in ("option_id", "expiration_date", "strike", "option_type"))
    if has_price and not has_option_identity:
        return DOMAIN_UNDERLYING

    return DOMAIN_UNKNOWN


def parse_datetime(value: Any, *, field: str, allow_date: bool = True) -> datetime:
    del allow_date  # retained for drop-in helper compatibility
    return parse_datetime_utc(
        value,
        field=field,
        date_only_policy="start_of_day",
        timezone_name="UTC",
        strict=False,
    )

def iso_datetime(value: Any, *, field: str) -> str:
    return parse_datetime(value, field=field).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def iso_date(value: Any, *, field: str) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "").strip()
    if not text:
        raise ContractValidationError(f"{field} is required")
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError as exc:
        raise ContractValidationError(f"invalid {field}: {value}") from exc


def row_date(row: dict[str, Any]) -> str:
    for field in ("date", "reference_date", "as_of_date", "available_at", "declared_available_at"):
        value = row.get(field)
        if value not in (None, ""):
            return iso_date(value, field=field)
    raise ContractValidationError("date is required")


def row_available_at(row: dict[str, Any]) -> str:
    for field in ("available_at", "declared_available_at"):
        value = row.get(field)
        if value not in (None, ""):
            return iso_datetime(value, field=field)
    raise ContractValidationError("available_at is required")


def optional_float(value: Any, *, field: str, nonnegative: bool = False, positive: bool = False) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ContractValidationError(f"invalid numeric field {field}: {value}") from exc
    if positive and number <= 0:
        raise ContractValidationError(f"{field} must be positive")
    if nonnegative and number < 0:
        raise ContractValidationError(f"{field} must be non-negative")
    return number


def source_quality_index(panel: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(panel, dict):
        return {}
    rows = panel.get("records")
    if not isinstance(rows, list):
        rows = []
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        source_id = row.get("source_id")
        if source_id not in (None, ""):
            index[str(source_id)] = dict(row)
    return index


def quality_state(source_id: Any, index: dict[str, dict[str, Any]]) -> tuple[str, list[str]]:
    row = index.get(str(source_id)) if source_id not in (None, "") else None
    if not row:
        return "WARN", ["SOURCE_QUALITY_UNKNOWN"]
    status = _normalized_token(row.get("quality_status") or row.get("status"))
    score = row.get("quality_score")
    reasons: list[str] = []
    if row.get("error_flag") is True or row.get("is_blocking") is True or status in _BLOCKING_QUALITY:
        return "BLOCK", ["SOURCE_BLOCKED"]
    if score not in (None, ""):
        try:
            score_value = float(score)
        except (TypeError, ValueError):
            score_value = None
        if score_value is not None:
            if score_value <= 0:
                return "BLOCK", ["SOURCE_QUALITY_ZERO"]
            if score_value < 0.8:
                reasons.append("SOURCE_QUALITY_LOW")
    if row.get("warning_flag") is True or status in {"WARN", "WARNING", "DEGRADED"}:
        reasons.append("SOURCE_WARNING")
    return ("WARN", reasons) if reasons else ("PASS", [])


def reject_blocked_source(row: dict[str, Any], quality_index: dict[str, dict[str, Any]]) -> tuple[str, list[str]]:
    status, reasons = quality_state(row.get("source_id"), quality_index)
    if status == "BLOCK":
        raise ContractValidationError(f"source_quality_blocked: {row.get('source_id')}")
    return status, reasons


def calendar_key(row: dict[str, Any]) -> tuple[str, str]:
    calendar_id = (
        row.get("calendar_id")
        or row.get("exchange")
        or row.get("market")
        or row.get("source_id")
        or "DEFAULT"
    )
    return str(calendar_id), row_date(row)


def calendar_index(panel: Any) -> dict[tuple[str, str], dict[str, Any]]:
    if not isinstance(panel, dict):
        return {}
    rows = panel.get("records")
    if not isinstance(rows, list):
        return {}
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            key = calendar_key(row)
        except ContractValidationError:
            continue
        index[key] = dict(row)
    return index


def find_calendar_row(row: dict[str, Any], index: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any] | None:
    day = row_date(row)
    candidates = [
        row.get("calendar_id"),
        row.get("exchange"),
        row.get("market"),
        row.get("source_id"),
        "DEFAULT",
    ]
    for candidate in candidates:
        if candidate in (None, ""):
            continue
        found = index.get((str(candidate), day))
        if found:
            return found
    same_day = [value for (calendar_id, calendar_day), value in index.items() if calendar_day == day]
    return same_day[0] if len(same_day) == 1 else None


def normalize_action_type(value: Any) -> str:
    token = _normalized_token(value)
    aliases = {
        "DIV": "DIVIDEND",
        "DIVIDEND": "DIVIDEND",
        "CASH_DIVIDEND": "DIVIDEND",
        "SPLIT": "SPLIT",
        "STOCK_SPLIT": "SPLIT",
        "REVERSE_SPLIT": "REVERSE_SPLIT",
        "BONUS": "BONUS",
        "RIGHTS": "RIGHTS",
        "RIGHTS_ISSUE": "RIGHTS",
        "SPINOFF": "SPINOFF",
        "SPIN_OFF": "SPINOFF",
    }
    return aliases.get(token, token or "OTHER")


def normalize_adjustment_policy(value: Any) -> str:
    token = _normalized_token(value)
    aliases = {
        "RAW": "RAW",
        "UNADJUSTED": "RAW",
        "SPLIT_ADJUSTED": "SPLIT_ADJUSTED",
        "ADJUSTED": "SPLIT_ADJUSTED",
        "TOTAL_RETURN_ADJUSTED": "TOTAL_RETURN_ADJUSTED",
        "TOTAL_RETURN": "TOTAL_RETURN_ADJUSTED",
    }
    return aliases.get(token, "UNKNOWN")


def same_business_values(left: dict[str, Any], right: dict[str, Any], fields: Iterable[str]) -> bool:
    return all(left.get(field) == right.get(field) for field in fields)
