from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .errors import TemporalContractError, TemporalErrorCode

_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True, slots=True)
class ResolvedInstant:
    value: datetime
    precision: str
    original_timezone: str
    fold: int | None

    def utc_text(self) -> str:
        return self.value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _zone(name: str, path: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise TemporalContractError(
            TemporalErrorCode.TIMEZONE_UNKNOWN,
            f"unknown IANA timezone {name!r}",
            path=path,
        ) from exc


def _roundtrip_valid(local: datetime, zone: ZoneInfo, fold: int) -> bool:
    aware = local.replace(tzinfo=zone, fold=fold)
    returned = aware.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
    return returned == local


def _localize(local: datetime, timezone_name: str, path: str, fold: int | None) -> datetime:
    zone = _zone(timezone_name, path)
    valid = [candidate for candidate in (0, 1) if _roundtrip_valid(local, zone, candidate)]
    if not valid:
        raise TemporalContractError(
            TemporalErrorCode.DST_NONEXISTENT,
            "local time does not exist in the declared timezone",
            path=path,
        )
    ambiguous = len(valid) == 2 and (
        local.replace(tzinfo=zone, fold=0).utcoffset()
        != local.replace(tzinfo=zone, fold=1).utcoffset()
    )
    if ambiguous and fold is None:
        raise TemporalContractError(
            TemporalErrorCode.DST_AMBIGUOUS,
            "ambiguous local time requires fold=0 or fold=1",
            path=path,
        )
    chosen = fold if fold is not None else valid[0]
    if chosen not in valid:
        raise TemporalContractError(
            TemporalErrorCode.DST_AMBIGUOUS,
            f"fold={chosen} is invalid for the local time",
            path=path,
        )
    return local.replace(tzinfo=zone, fold=chosen)


def _date_time(value: date, policy: str) -> datetime:
    if policy == "start_of_day":
        return datetime.combine(value, time.min)
    if policy == "end_of_day":
        return datetime.combine(value, time.max)
    raise TemporalContractError(
        TemporalErrorCode.TEMPORAL_VALUE_INVALID,
        f"unsupported date-only policy {policy!r}",
    )


def resolve_instant(
    value: Any,
    *,
    path: str,
    timezone_name: str,
    date_only_policy: str,
    fold: int | None = None,
) -> ResolvedInstant:
    if value in (None, ""):
        raise TemporalContractError(
            TemporalErrorCode.TEMPORAL_VALUE_MISSING,
            "temporal value is missing",
            path=path,
        )
    precision = "SECOND"
    if isinstance(value, datetime):
        parsed = value
        precision = "MICROSECOND" if value.microsecond else "SECOND"
    elif isinstance(value, date):
        parsed = _date_time(value, date_only_policy)
        precision = "DATE"
    elif isinstance(value, str):
        text = value.strip()
        if _DATE_ONLY.fullmatch(text):
            parsed = _date_time(date.fromisoformat(text), date_only_policy)
            precision = "DATE"
        else:
            normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
            try:
                parsed = datetime.fromisoformat(normalized)
            except ValueError as exc:
                raise TemporalContractError(
                    TemporalErrorCode.TEMPORAL_VALUE_INVALID,
                    f"invalid ISO-8601 value {value!r}",
                    path=path,
                ) from exc
            precision = "MICROSECOND" if parsed.microsecond else "SECOND"
    else:
        raise TemporalContractError(
            TemporalErrorCode.TEMPORAL_VALUE_INVALID,
            "temporal value must be date, datetime, or ISO-8601 string",
            path=path,
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = _localize(parsed, timezone_name, path, fold)
    original_timezone = getattr(parsed.tzinfo, "key", None) or str(parsed.tzinfo)
    return ResolvedInstant(parsed.astimezone(UTC), precision, original_timezone, fold)


def optional_instant(
    value: Any,
    *,
    path: str,
    timezone_name: str,
    date_only_policy: str,
    fold: int | None = None,
) -> ResolvedInstant | None:
    if value in (None, ""):
        return None
    return resolve_instant(
        value,
        path=path,
        timezone_name=timezone_name,
        date_only_policy=date_only_policy,
        fold=fold,
    )
