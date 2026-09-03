"""Temporal primitives for P2.S2.

P2.S2 is the single authority for point-in-time availability semantics.  This
module is intentionally provider-neutral: provider-specific extraction belongs
in P1; S2 consumes only captured metadata and materialized raw records.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ._module_executor import ContractValidationError

TEMPORAL_POLICY_VERSION = "p2.temporal.v1"
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PIT_VALID_STATUSES = {"VALID", "PROVIDER_TIMESTAMP", "RELEASE_TIMESTAMP", "VINTAGE_DATE", "TIMESTAMP_PIT_VALIDATED"}
_PIT_BLOCKED_STATUSES = {"UNPROVEN", "DATE_LEVEL_PIT_UNPROVEN", "SNAPSHOT_ONLY", "SNAPSHOT_OR_DATE_LEVEL_ONLY"}


def optional_rows(value: Any) -> list[dict]:
    """Read an optional artifact envelope without synthesizing data."""
    if value in (None, {}):
        return []
    if isinstance(value, list):
        return [dict(row) for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        for key in ("records", "rows", "items", "sources", "checks", "errors"):
            rows = value.get(key)
            if isinstance(rows, list):
                return [dict(row) for row in rows if isinstance(row, dict)]
        if value.get("source"):
            raise ContractValidationError("source_quality_panel cannot be synthesized from source")
        return []
    raise ContractValidationError("source_quality_panel must be an artifact envelope or record list")


def quality_index(value: Any) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for row in optional_rows(value):
        source_id = row.get("source_id")
        if source_id in (None, ""):
            continue
        key = str(source_id)
        if key in index:
            raise ContractValidationError(f"P2_S2_M01_SOURCE_QUALITY_DUPLICATE: source_id={key}")
        index[key] = row
    return index


def _timezone_name(row: dict, config: dict, source_id: str | None) -> tuple[str | None, bool]:
    explicit = row.get("timezone") or row.get("source_timezone")
    if explicit:
        return str(explicit), False

    by_source = config.get("timezone_by_source") or config.get("default_timezone_by_source") or {}
    if source_id and isinstance(by_source, dict) and by_source.get(source_id):
        return str(by_source[source_id]), False

    default_timezone = config.get("default_timezone")
    if default_timezone:
        return str(default_timezone), False

    if not bool(config.get("strict_temporal_validation", False)):
        return "UTC", True
    return None, False


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ContractValidationError(f"P2_S2_M01_UNKNOWN_TIMEZONE: {name}") from exc


def _iso_utc(value: datetime) -> str:
    utc_value = value.astimezone(timezone.utc)
    if utc_value.microsecond:
        return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    return utc_value.isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_instant(
    value: Any,
    *,
    timezone_name: str | None,
    date_only_policy: str = "end_of_day",
    strict: bool,
    error_code: str,
) -> tuple[datetime, str, bool]:
    """Parse a temporal value into a timezone-aware instant.

    Returns (UTC datetime, temporal precision, timezone_assumed).
    """
    if value in (None, ""):
        raise ContractValidationError(f"{error_code}: missing temporal value")

    assumed = False
    if isinstance(value, datetime):
        parsed = value
        precision = "MICROSECOND" if value.microsecond else "SECOND"
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.max if date_only_policy == "end_of_day" else time.min)
        precision = "DATE"
    else:
        text = str(value).strip()
        if _DATE_ONLY.fullmatch(text):
            parsed_date = date.fromisoformat(text)
            parsed = datetime.combine(parsed_date, time.max if date_only_policy == "end_of_day" else time.min)
            precision = "DATE"
        else:
            normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
            try:
                parsed = datetime.fromisoformat(normalized)
            except ValueError as exc:
                raise ContractValidationError(f"{error_code}: invalid timestamp {value!r}") from exc
            precision = "MICROSECOND" if parsed.microsecond else ("SECOND" if parsed.second else "MINUTE")

    if parsed.tzinfo is None:
        if not timezone_name:
            if strict:
                raise ContractValidationError(f"P2_S2_M01_UNKNOWN_TIMEZONE: value={value!r}")
            timezone_name = "UTC"
            assumed = True
        parsed = parsed.replace(tzinfo=_zone(timezone_name))

    return parsed.astimezone(timezone.utc), precision, assumed


def parse_datetime_utc(
    value: Any,
    *,
    field: str,
    date_only_policy: str = "start_of_day",
    timezone_name: str = "UTC",
    strict: bool = False,
) -> datetime:
    """Shared P2 parser for timezone-aware UTC datetimes.

    S2 owns temporal semantics. Downstream subphases reuse this helper instead
    of maintaining independent parsers. ``date_only_policy`` is explicit so a
    business date and an as-of cutoff cannot accidentally share semantics.
    """
    parsed, _, _ = parse_instant(
        value,
        timezone_name=timezone_name,
        date_only_policy=date_only_policy,
        strict=strict,
        error_code=f"P2_TEMPORAL_INVALID_{field.upper()}",
    )
    return parsed


def parse_as_of_cutoff(value: Any, config: dict | None = None) -> datetime | None:
    if value in (None, ""):
        return None
    cfg = config or {}
    timezone_name = str(cfg.get("as_of_timezone") or cfg.get("default_timezone") or "UTC")
    return parse_datetime_utc(
        value,
        field="as_of_date",
        date_only_policy="end_of_day",
        timezone_name=timezone_name,
        strict=False,
    )


def normalize_reference_date(value: Any) -> str | None:
    """Preserve reference-time meaning without converting it into availability."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if _DATE_ONLY.fullmatch(text):
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError as exc:
            raise ContractValidationError(f"P2_S2_M01_INVALID_REFERENCE_DATE: {value!r}") from exc
    return text


def derive_available_at(row: dict, config: dict) -> tuple[Any, str]:
    """Resolve availability using a fixed, auditable precedence order."""
    if row.get("available_at") not in (None, ""):
        return row["available_at"], "EXPLICIT_AVAILABLE_AT"

    source_id = str(row.get("source_id")) if row.get("source_id") not in (None, "") else None
    mappings = config.get("availability_field_by_source") or {}
    if source_id and isinstance(mappings, dict):
        field_name = mappings.get(source_id)
        if field_name and row.get(str(field_name)) not in (None, ""):
            return row[str(field_name)], f"SOURCE_FIELD_MAPPING:{field_name}"

    if row.get("declared_available_at") not in (None, ""):
        return row["declared_available_at"], "DECLARED_AVAILABLE_AT"

    raise ContractValidationError("P2_S2_M01_AVAILABLE_AT_MISSING: available_at/declared_available_at not found")


def normalize_record_temporal(row: dict, quality_by_source: dict[str, dict], config: dict) -> dict:
    strict = bool(config.get("strict_temporal_validation", False))
    source_id = str(row.get("source_id")) if row.get("source_id") not in (None, "") else None
    timezone_name, timezone_assumed = _timezone_name(row, config, source_id)

    raw_available_at, temporal_source = derive_available_at(row, config)
    available_dt, precision, parser_assumed = parse_instant(
        raw_available_at,
        timezone_name=timezone_name,
        date_only_policy=str(config.get("date_only_availability_policy") or "end_of_day"),
        strict=strict,
        error_code="P2_S2_M01_INVALID_TIMESTAMP",
    )
    timezone_assumed = timezone_assumed or parser_assumed

    source_pit_status = str(row.get("pit_status") or "").strip().upper()
    availability_basis = str(
        row.get("availability_basis")
        or row.get("availability_precision")
        or row.get("availability_policy")
        or "EXPLICIT_TIMESTAMP_UNATTESTED"
    )
    if bool(config.get("reject_assumed_timezone", False)) and timezone_assumed:
        raise ContractValidationError("P2_S2_M01_ASSUMED_TIMEZONE_REJECTED")
    daily_mode = str(config.get("pit_granularity") or "INSTANT").upper() == "DAILY"
    normalized_pit_status = source_pit_status or "UNPROVEN"
    if bool(config.get("require_pit_provenance", False)):
        if not source_pit_status:
            raise ContractValidationError("P2_S2_M01_PIT_PROVENANCE_MISSING")
        if source_pit_status in _PIT_BLOCKED_STATUSES:
            daily_policy_allowed = (
                daily_mode
                and bool(config.get("allow_daily_pit_policy", False))
                and source_pit_status == "DATE_LEVEL_PIT_UNPROVEN"
                and availability_basis == "BAR_CLOSE_POLICY"
                and str(row.get("record_domain") or "").upper() in {"UNDERLYING", "BENCHMARK"}
            )
            if not daily_policy_allowed:
                raise ContractValidationError(
                    f"P2_S2_M01_PIT_UNPROVEN: status={source_pit_status} basis={availability_basis}"
                )
            normalized_pit_status = "VALID_DAILY_POLICY"
        elif daily_mode and source_pit_status in {"DATE_LEVEL_PIT_VALIDATED", "TIMESTAMP_PIT_VALIDATED", "VALID"}:
            normalized_pit_status = "VALID_DAILY"

    output = dict(row)
    output["available_at"] = _iso_utc(available_dt)
    output["temporal_precision"] = precision
    output["temporal_source"] = temporal_source
    output["availability_basis"] = availability_basis
    output["pit_granularity"] = "DAILY" if daily_mode else "INSTANT"
    output["available_date"] = available_dt.date().isoformat()
    output["pit_status"] = normalized_pit_status
    output["pit_normalized"] = True
    output["temporal_policy_version"] = TEMPORAL_POLICY_VERSION
    output["timezone"] = "UTC"
    if timezone_assumed:
        output["timezone_assumed"] = True

    reference = row.get("reference_date", row.get("source_reference_date"))
    normalized_reference = normalize_reference_date(reference)
    if normalized_reference is not None:
        output["reference_date"] = normalized_reference

    retrieved_raw = row.get("retrieved_at", row.get("ingested_at"))
    if retrieved_raw not in (None, ""):
        retrieved_dt, _, retrieved_assumed = parse_instant(
            retrieved_raw,
            timezone_name=timezone_name,
            date_only_policy="end_of_day",
            strict=strict,
            error_code="P2_S2_M01_INVALID_RETRIEVED_AT",
        )
        output["retrieved_at"] = _iso_utc(retrieved_dt)
        if retrieved_dt < available_dt:
            raise ContractValidationError(
                "P2_S2_M01_RETRIEVED_BEFORE_AVAILABLE: "
                f"retrieved_at={output['retrieved_at']} available_at={output['available_at']}"
            )
        if retrieved_assumed:
            output["retrieved_timezone_assumed"] = True

    for field in ("revision_id", "vintage_date", "valid_from", "valid_until", "realtime_start", "realtime_end"):
        if field in row:
            output[field] = row[field]

    quality = quality_by_source.get(source_id or "")
    if quality is None:
        if bool(config.get("strict_source_quality", False)):
            raise ContractValidationError(f"P2_S2_M01_SOURCE_QUALITY_MISSING: source_id={source_id}")
    else:
        for source_field, output_field in (
            ("quality_score", "source_quality_score"),
            ("quality_status", "source_quality_status"),
            ("critical", "critical_source"),
        ):
            if quality.get(source_field) not in (None, ""):
                output[output_field] = quality[source_field]
        if str(quality.get("quality_status") or "").upper() == "BLOCK":
            output["pit_status"] = "SOURCE_BLOCKED"
            if bool(quality.get("critical")) and bool(config.get("fail_on_blocked_critical_source", False)):
                raise ContractValidationError(f"P2_S2_M01_BLOCKED_CRITICAL_SOURCE: source_id={source_id}")

    return output


def parse_cutoff(value: Any, config: dict) -> datetime | None:
    return parse_as_of_cutoff(value, config)


def enforce_cutoff(row: dict, cutoff: datetime | None) -> None:
    if cutoff is None:
        return
    available_dt, _, _ = parse_instant(
        row.get("available_at"),
        timezone_name="UTC",
        strict=True,
        error_code="P2_S2_M01_INVALID_TIMESTAMP",
    )
    if available_dt > cutoff:
        raise ContractValidationError(
            f"no_future_availability violation: available_at={row.get('available_at')} cutoff={_iso_utc(cutoff)}"
        )
