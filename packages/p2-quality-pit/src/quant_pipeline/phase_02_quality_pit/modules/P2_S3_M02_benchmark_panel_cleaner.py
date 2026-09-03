from __future__ import annotations

from ._module_executor import ContractValidationError
from ._p2_semantic_helpers import artifact, no_forbidden_rows, records, require_inputs
from ._s3_market_helpers import (
    DOMAIN_BENCHMARK,
    infer_domain,
    reject_blocked_source,
    row_available_at,
    row_date,
    same_business_values,
    source_quality_index,
)


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    required = ["identifier_harmonized_bundle", "source_quality_panel"]
    require_inputs(inputs, required)

    source_rows = records(inputs[required[0]], required[0])
    no_forbidden_rows(source_rows)
    quality_index = source_quality_index(inputs[required[1]])

    clean_by_key: dict[tuple[str, str], dict] = {}
    for row in source_rows:
        if infer_domain(row) != DOMAIN_BENCHMARK:
            continue
        quality_status, quality_reasons = reject_blocked_source(row, quality_index)
        benchmark_id = row.get("benchmark_id") or row.get("canonical_instrument_id")
        if benchmark_id in (None, ""):
            raise ContractValidationError("benchmark_id is required")
        clean = {
            **row,
            "benchmark_id": str(benchmark_id),
            "date": row_date(row),
            "available_at": row_available_at(row),
            "source_quality_status": quality_status,
            "source_quality_reasons": quality_reasons,
        }
        key = (clean["benchmark_id"], clean["date"])
        previous = clean_by_key.get(key)
        if previous is not None:
            comparable = ("benchmark_id", "date", "close", "value", "source_id", "available_at")
            if not same_business_values(previous, clean, comparable):
                raise ContractValidationError(f"benchmark_key_unique violation: {key}")
            continue
        clean_by_key[key] = clean

    clean_rows = list(clean_by_key.values())
    return {
        "module_id": "P2.S3.M02",
        "module_name": "benchmark_panel_cleaner",
        "phase": "phase_02_quality_pit",
        "subphase": "P2.S3",
        "contract": "P2_S3_M02_benchmark_panel_cleaner.yaml",
        "required_inputs": required,
        "outputs": {
            "clean_benchmark_panel": artifact(
                "clean-benchmark-panel",
                clean_rows,
                config,
                benchmark_key_unique=True,
                no_prediction=True,
            )
        },
    }
