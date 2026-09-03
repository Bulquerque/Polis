from __future__ import annotations

from ._module_executor import ContractValidationError
from ._p2_semantic_helpers import artifact, no_forbidden_rows, records, require_inputs
from ._s3_market_helpers import (
    calendar_index,
    find_calendar_row,
    optional_float,
    quality_state,
    source_quality_index,
)


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    required = ["clean_underlying_panel", "clean_calendar_panel", "source_quality_panel"]
    require_inputs(inputs, required)

    source_rows = records(inputs[required[0]], required[0])
    no_forbidden_rows(source_rows)
    calendars = calendar_index(inputs[required[1]])
    quality_index = source_quality_index(inputs[required[2]])

    trade_rows: list[dict] = []
    for row in source_rows:
        close = optional_float(row.get("close"), field="close", nonnegative=True)
        reference_price = optional_float(row.get("reference_price_t"), field="reference_price_t", nonnegative=True)
        if reference_price is None:
            reference_price = close
        if reference_price is None:
            raise ContractValidationError("tradable_price_present violation")

        bid = optional_float(row.get("bid"), field="bid", nonnegative=True)
        ask = optional_float(row.get("ask"), field="ask", nonnegative=True)
        if bid is not None and ask is not None and bid > ask:
            raise ContractValidationError("crossed_market violation")

        calendar_row = find_calendar_row(row, calendars) if calendars else None
        calendar_aligned = calendar_row is not None
        alignment_status = "ALIGNED" if calendar_aligned else row.get("calendar_alignment_status", "UNKNOWN")
        market_open = calendar_row.get("is_trading_day") is True if calendar_row else row.get("is_trading_day") is True
        quality_status, quality_reasons = quality_state(row.get("source_id"), quality_index)

        reasons: list[str] = list(quality_reasons)
        if not market_open:
            reasons.append("MARKET_CLOSED_OR_UNKNOWN")
        if quality_status == "BLOCK":
            reasons.append("SOURCE_BLOCKED")
        if bid is None or ask is None:
            reasons.append("QUOTE_NOT_AVAILABLE")

        tradable = market_open and quality_status != "BLOCK" and reference_price >= 0
        cost_estimate = optional_float(row.get("cost_estimate"), field="cost_estimate", nonnegative=True)
        if cost_estimate is None and bid is not None and ask is not None:
            cost_estimate = ask - bid
        liquidity_score = optional_float(row.get("liquidity_score"), field="liquidity_score", nonnegative=True)
        execution_data_ready = tradable and bid is not None and ask is not None
        execution_readiness_status = (
            "READY" if execution_data_ready
            else ("DEGRADED" if tradable else "BLOCKED")
        )

        trade_rows.append(
            {
                **row,
                "reference_price_t": reference_price,
                "bid": bid,
                "ask": ask,
                "volume": optional_float(row.get("volume"), field="volume", nonnegative=True),
                "financial_volume": optional_float(row.get("financial_volume"), field="financial_volume", nonnegative=True),
                "tradability_flag": tradable,
                "market_tradable_flag": tradable,
                "tradability_reasons": sorted(set(reasons)),
                "execution_data_ready": execution_data_ready,
                "execution_readiness_status": execution_readiness_status,
                "cost_estimate": cost_estimate,
                "liquidity_score": liquidity_score,
                "calendar_aligned": calendar_aligned,
                "calendar_alignment_status": alignment_status,
            }
        )

    calendar_alignment_checked = all("calendar_alignment_status" in row for row in trade_rows)
    calendar_alignment_complete = all(row.get("calendar_aligned") is True for row in trade_rows)
    output = artifact(
        "clean-underlying-trade-panel",
        trade_rows,
        config,
        tradable_price_present=all(row.get("reference_price_t") is not None for row in trade_rows),
        calendar_aligned=calendar_alignment_checked,
        calendar_alignment_complete=calendar_alignment_complete,
        no_candidate_creation=True,
        execution_readiness_evaluated=True,
    )
    # Preserve the legacy top-level contract flag without overwriting the more
    # precise per-record alignment state copied by artifact().
    output["calendar_aligned"] = calendar_alignment_checked
    output["calendar_alignment_complete"] = calendar_alignment_complete
    return {
        "module_id": "P2.S3.M06",
        "module_name": "underlying_trade_panel_builder",
        "phase": "phase_02_quality_pit",
        "subphase": "P2.S3",
        "contract": "P2_S3_M06_underlying_trade_panel_builder.yaml",
        "required_inputs": required,
        "outputs": {"clean_underlying_trade_panel": output},
    }
