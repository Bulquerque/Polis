from __future__ import annotations

from collections import defaultdict

from ._module_executor import ContractValidationError
from ._p2_semantic_helpers import artifact, no_forbidden_rows, records, require_inputs
from ._s3_market_helpers import (
    DOMAIN_UNDERLYING,
    calendar_index,
    find_calendar_row,
    infer_domain,
    normalize_adjustment_policy,
    optional_float,
    parse_datetime,
    reject_blocked_source,
    row_available_at,
    row_date,
    source_quality_index,
)


def _actions_by_underlying(panel: dict) -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = defaultdict(list)
    for row in records(panel, "clean_corporate_actions_panel") if isinstance(panel, dict) and panel.get("records") is not None else []:
        underlying = row.get("underlying")
        if underlying not in (None, ""):
            index[str(underlying)].append(row)
    return index


def _applicable_adjustment(row: dict, actions: list[dict]) -> tuple[float, list[str]]:
    policy = normalize_adjustment_policy(row.get("price_adjustment_policy") or row.get("adjustment_policy"))
    direct_factor = optional_float(row.get("adjustment_factor"), field="adjustment_factor", positive=True)
    if direct_factor is not None:
        return direct_factor, ["DIRECT_FACTOR"]
    if policy in {"SPLIT_ADJUSTED", "TOTAL_RETURN_ADJUSTED"}:
        return 1.0, ["PROVIDER_ALREADY_ADJUSTED"]

    observation_date = row_date(row)
    as_of = parse_datetime(row_available_at(row), field="available_at")
    factors: list[float] = []
    for action in actions:
        factor = optional_float(action.get("adjustment_factor"), field="adjustment_factor", positive=True)
        effective_date = action.get("effective_date") or action.get("ex_date")
        available_at = action.get("available_at")
        if factor is None or not effective_date or not available_at:
            continue
        if str(effective_date)[:10] <= observation_date and parse_datetime(available_at, field="available_at") <= as_of:
            factors.append(factor)
    if not factors:
        return 1.0, ["NO_APPLICABLE_ACTION"]
    factor = 1.0
    for value in factors:
        factor *= value
    return factor, ["PIT_ACTION_FACTOR"]


def _validated_ohlc(row: dict) -> tuple[float | None, float | None, float | None, float]:
    try:
        close = optional_float(row.get("close", row.get("price")), field="close", nonnegative=True)
        open_value = optional_float(row.get("open"), field="open", nonnegative=True)
        high_value = optional_float(row.get("high"), field="high", nonnegative=True)
        low_value = optional_float(row.get("low"), field="low", nonnegative=True)
    except ContractValidationError as exc:
        if "non-negative" in str(exc):
            raise ContractValidationError(f"price_non_negative violation: {exc}") from exc
        raise
    if close is None:
        raise ContractValidationError("tradable close/price is required for underlying record")
    observed = [value for value in (open_value, close, low_value) if value is not None]
    if high_value is not None and observed and high_value < max(observed):
        raise ContractValidationError("ohlc_consistency violation: high below observed price")
    observed_high = [value for value in (open_value, close, high_value) if value is not None]
    if low_value is not None and observed_high and low_value > min(observed_high):
        raise ContractValidationError("ohlc_consistency violation: low above observed price")
    return open_value, high_value, low_value, close


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    required = [
        "identifier_harmonized_bundle",
        "source_quality_panel",
        "clean_calendar_panel",
        "clean_corporate_actions_panel",
    ]
    require_inputs(inputs, required)

    source_rows = records(inputs[required[0]], required[0])
    no_forbidden_rows(source_rows)
    quality_index = source_quality_index(inputs[required[1]])
    calendars = calendar_index(inputs[required[2]])
    actions_index = _actions_by_underlying(inputs[required[3]])

    clean_by_key: dict[tuple[str, str], dict] = {}
    for row in source_rows:
        if infer_domain(row) != DOMAIN_UNDERLYING:
            continue
        quality_status, quality_reasons = reject_blocked_source(row, quality_index)
        underlying = row.get("underlying") or row.get("canonical_instrument_id") or row.get("source_id")
        if underlying in (None, ""):
            raise ContractValidationError("underlying is required")
        date_value = row_date(row)
        available_at = row_available_at(row)
        open_value, high_value, low_value, close = _validated_ohlc(row)
        volume = optional_float(row.get("volume"), field="volume", nonnegative=True)
        financial_volume = optional_float(row.get("financial_volume"), field="financial_volume", nonnegative=True)

        calendar_row = find_calendar_row(row, calendars) if calendars else None
        if calendar_row is None:
            is_trading_day = False
            calendar_status = "UNKNOWN"
            quality_reasons = [*quality_reasons, "CALENDAR_UNKNOWN"]
        else:
            is_trading_day = calendar_row.get("is_trading_day") is True
            calendar_status = "ALIGNED"

        adjustment_factor, adjustment_reasons = _applicable_adjustment(row, actions_index.get(str(underlying), []))
        quality_reasons = [*quality_reasons, *adjustment_reasons]
        policy = normalize_adjustment_policy(row.get("price_adjustment_policy") or row.get("adjustment_policy"))
        if policy == "UNKNOWN":
            quality_reasons.append("ADJUSTMENT_POLICY_UNKNOWN")

        clean = {
            **row,
            "date": date_value,
            "as_of_date": row.get("as_of_date") or available_at,
            "available_at": available_at,
            "underlying": str(underlying),
            "open": open_value,
            "high": high_value,
            "low": low_value,
            "close": close,
            "volume": volume,
            "financial_volume": financial_volume,
            "adjustment_factor": adjustment_factor,
            "is_trading_day": is_trading_day,
            "quality_flag": "PASS" if quality_status == "PASS" and not quality_reasons else "WARN",
            "source_quality_status": quality_status,
            "quality_reasons": sorted(set(quality_reasons)),
            "calendar_alignment_status": calendar_status,
            "price_adjustment_policy": policy,
            "corporate_actions_applied_pit": True,  # legacy compatibility flag
            "corporate_actions_resolved_pit": True,
            "price_values_adjusted_by_p2": False,
            "resolved_adjustment_factor": adjustment_factor,
        }
        key = (clean["underlying"], clean["date"])
        previous = clean_by_key.get(key)
        if previous is not None:
            fields = ("open", "high", "low", "close", "volume", "financial_volume", "adjustment_factor", "source_id")
            if any(previous.get(field) != clean.get(field) for field in fields):
                raise ContractValidationError(f"underlying_date_unique violation: conflicting rows for {key}")
            continue
        clean_by_key[key] = clean

    clean_rows = list(clean_by_key.values())
    return {
        "module_id": "P2.S3.M05",
        "module_name": "underlying_panel_cleaner",
        "phase": "phase_02_quality_pit",
        "subphase": "P2.S3",
        "contract": "P2_S3_M05_underlying_panel_cleaner.yaml",
        "required_inputs": required,
        "outputs": {
            "clean_underlying_panel": artifact(
                "clean-underlying-panel",
                clean_rows,
                config,
                underlying_date_unique=True,
                price_non_negative=True,
                corporate_actions_applied_pit=True,
                corporate_actions_resolved_pit=True,
                price_values_adjusted_by_p2=False,
                corporate_action_semantics="pit_factor_resolved_prices_not_rewritten",
            )
        },
    }
