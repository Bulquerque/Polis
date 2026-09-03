from __future__ import annotations

from ._module_executor import ContractValidationError
from ._p2_semantic_helpers import artifact, no_forbidden_rows, records, require_inputs
from ._s3_market_helpers import (
    DOMAIN_CALENDAR,
    calendar_key,
    infer_domain,
    reject_blocked_source,
    row_available_at,
    source_quality_index,
)


def _parse_trading_flag(value: object) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    token = str(value).strip().lower()
    if token in {"true", "1", "yes", "y", "open", "trading_day"}:
        return True
    if token in {"false", "0", "no", "n", "closed", "non_trading_day"}:
        return False
    raise ContractValidationError(f"P2_S3_M03_INVALID_TRADING_FLAG: {value!r}")


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    required = ["identifier_harmonized_bundle", "source_quality_panel"]
    require_inputs(inputs, required)

    source_rows = records(inputs[required[0]], required[0])
    no_forbidden_rows(source_rows)
    quality_index = source_quality_index(inputs[required[1]])

    calendar_by_key: dict[tuple[str, str], dict] = {}
    for row in source_rows:
        if infer_domain(row) != DOMAIN_CALENDAR:
            continue
        quality_status, quality_reasons = reject_blocked_source(row, quality_index)
        key = calendar_key(row)
        trading_value = row.get("is_trading_day")
        if trading_value is None and "trading_day_flag" in row:
            trading_value = row.get("trading_day_flag")
        is_trading_day = _parse_trading_flag(trading_value)
        clean = {
            **row,
            "calendar_id": key[0],
            "date": key[1],
            "is_trading_day": is_trading_day,
            "trading_day_flag": is_trading_day,
            "source_quality_status": quality_status,
            "source_quality_reasons": quality_reasons,
        }
        if row.get("available_at") not in (None, "") or row.get("declared_available_at") not in (None, ""):
            clean["available_at"] = row_available_at(row)
        previous = calendar_by_key.get(key)
        if previous is not None:
            fields = ("is_trading_day", "session_open", "session_close", "early_close", "holiday_code")
            if any(previous.get(field) != clean.get(field) for field in fields):
                raise ContractValidationError(f"calendar_dates_unique violation: {key}")
            continue
        calendar_by_key[key] = clean

    calendar_rows = list(calendar_by_key.values())
    trading_day_flag_present = all("is_trading_day" in row for row in calendar_rows)
    return {
        "module_id": "P2.S3.M03",
        "module_name": "calendar_panel_builder",
        "phase": "phase_02_quality_pit",
        "subphase": "P2.S3",
        "contract": "P2_S3_M03_calendar_panel_builder.yaml",
        "required_inputs": required,
        "outputs": {
            "clean_calendar_panel": artifact(
                "clean-calendar-panel",
                calendar_rows,
                config,
                calendar_dates_unique=True,
                trading_day_flag_present=trading_day_flag_present,
            )
        },
    }
