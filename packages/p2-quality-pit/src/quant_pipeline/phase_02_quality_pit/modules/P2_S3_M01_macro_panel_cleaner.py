from __future__ import annotations

from ._p2_semantic_helpers import artifact, no_forbidden_rows, records, require_inputs
from ._s3_market_helpers import (
    DOMAIN_MACRO,
    infer_domain,
    reject_blocked_source,
    row_available_at,
    row_date,
    source_quality_index,
)


def _region(row: dict) -> str | None:
    value = row.get("region") or row.get("country") or row.get("geography")
    if value in (None, ""):
        return None
    token = str(value).strip().upper().replace(" ", "_")
    if token in {"BR", "BRA", "BRAZIL", "BRASIL"}:
        return "BR"
    if token in {"US", "USA", "UNITED_STATES", "UNITED_STATES_OF_AMERICA"}:
        return "US"
    return None


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    required = ["identifier_harmonized_bundle", "source_quality_panel"]
    require_inputs(inputs, required)

    source_rows = records(inputs[required[0]], required[0])
    no_forbidden_rows(source_rows)
    quality_index = source_quality_index(inputs[required[1]])

    br_rows: list[dict] = []
    us_rows: list[dict] = []
    unclassified_count = 0

    for row in source_rows:
        if infer_domain(row) != DOMAIN_MACRO:
            continue
        quality_status, quality_reasons = reject_blocked_source(row, quality_index)
        region = _region(row)
        if region is None:
            unclassified_count += 1
            continue
        clean = {
            **row,
            "date": row.get("reference_date") or row_date(row),
            "available_at": row_available_at(row),
            "macro_region": region,
            "pit_date": True,
            "source_quality_status": quality_status,
            "source_quality_reasons": quality_reasons,
        }
        (br_rows if region == "BR" else us_rows).append(clean)

    outputs = {
        "clean_macro_br_panel": artifact(
            "clean-macro-br-panel",
            br_rows,
            config,
            macro_dates_pit=True,
            no_target_creation=True,
            unclassified_macro_records=unclassified_count,
        ),
        "clean_macro_us_panel": artifact(
            "clean-macro-us-panel",
            us_rows,
            config,
            macro_dates_pit=True,
            no_target_creation=True,
            unclassified_macro_records=unclassified_count,
        ),
    }
    return {
        "module_id": "P2.S3.M01",
        "module_name": "macro_panel_cleaner",
        "phase": "phase_02_quality_pit",
        "subphase": "P2.S3",
        "contract": "P2_S3_M01_macro_panel_cleaner.yaml",
        "required_inputs": required,
        "outputs": outputs,
    }
