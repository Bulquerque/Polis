from __future__ import annotations

from ._module_executor import ContractValidationError
from ._p2_semantic_helpers import artifact, no_forbidden_rows, records, require_inputs
from ._s3_market_helpers import (
    DOMAIN_CORPORATE_ACTION,
    infer_domain,
    normalize_action_type,
    optional_float,
    reject_blocked_source,
    row_available_at,
    source_quality_index,
)


def _optional_date(row: dict, *fields: str) -> str | None:
    from ._s3_market_helpers import iso_date

    for field in fields:
        value = row.get(field)
        if value not in (None, ""):
            return iso_date(value, field=field)
    return None


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    required = ["identifier_harmonized_bundle", "source_quality_panel", "clean_calendar_panel"]
    require_inputs(inputs, required)

    source_rows = records(inputs[required[0]], required[0])
    no_forbidden_rows(source_rows)
    quality_index = source_quality_index(inputs[required[1]])

    clean_rows: list[dict] = []
    seen: set[tuple] = set()
    for row in source_rows:
        if infer_domain(row) != DOMAIN_CORPORATE_ACTION:
            continue
        quality_status, quality_reasons = reject_blocked_source(row, quality_index)
        available_at = row_available_at(row)
        action_type = normalize_action_type(row.get("action_type"))
        underlying = row.get("underlying") or row.get("canonical_instrument_id") or row.get("source_id")
        if underlying in (None, ""):
            raise ContractValidationError("corporate action underlying is required")
        effective_date = _optional_date(row, "effective_date", "ex_date", "date")
        ex_date = _optional_date(row, "ex_date")
        record_date = _optional_date(row, "record_date")
        payment_date = _optional_date(row, "payment_date")
        adjustment_factor = optional_float(row.get("adjustment_factor"), field="adjustment_factor", positive=True)
        cash_amount = optional_float(row.get("cash_amount"), field="cash_amount", nonnegative=True)
        ratio = optional_float(row.get("ratio"), field="ratio", positive=True)
        action_key = (
            str(underlying),
            action_type,
            effective_date,
            ex_date,
            row.get("action_id"),
            adjustment_factor,
            cash_amount,
            ratio,
        )
        if action_key in seen:
            continue
        seen.add(action_key)
        clean_rows.append(
            {
                **row,
                "underlying": str(underlying),
                "action_type": action_type,
                "available_at": available_at,
                "effective_date": effective_date,
                "ex_date": ex_date,
                "record_date": record_date,
                "payment_date": payment_date,
                "adjustment_factor": adjustment_factor,
                "cash_amount": cash_amount,
                "ratio": ratio,
                "source_quality_status": quality_status,
                "source_quality_reasons": quality_reasons,
            }
        )

    return {
        "module_id": "P2.S3.M04",
        "module_name": "corporate_actions_cleaner",
        "phase": "phase_02_quality_pit",
        "subphase": "P2.S3",
        "contract": "P2_S3_M04_corporate_actions_cleaner.yaml",
        "required_inputs": required,
        "outputs": {
            "clean_corporate_actions_panel": artifact(
                "clean-corporate-actions-panel",
                clean_rows,
                config,
                corporate_action_available_at_present=True,
                adjustment_factor_not_future=True,
                temporal_semantics="knowledge_time_separated_from_effective_time",
            )
        },
    }
