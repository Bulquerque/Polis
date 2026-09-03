from __future__ import annotations

from ..s5_context import assert_no_forbidden_recursive, clean_s5_records
from ._p2_semantic_helpers import artifact, records, require_inputs


MODULE_ID = "P2.S5.M01"
MODULE_NAME = "context_document_event_cleaner"
PHASE = "phase_02_quality_pit"
SUBPHASE = "P2.S5"
CONTRACT = "P2_S5_M01_context_document_event_cleaner.yaml"


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    required = ["identifier_harmonized_bundle", "source_quality_panel"]
    require_inputs(inputs, required)

    input_rows = records(inputs["identifier_harmonized_bundle"], required[0])
    cleaned = clean_s5_records(input_rows, inputs["source_quality_panel"])

    assert_no_forbidden_recursive(
        cleaned.context_rows, "clean_context_source_panel.records"
    )
    assert_no_forbidden_recursive(
        cleaned.document_rows, "clean_document_panel.records"
    )
    assert_no_forbidden_recursive(
        cleaned.event_rows, "clean_event_reference_panel.records"
    )

    common_metrics = {
        "input_count": len(input_rows),
        "rejected_count": cleaned.rejected_count,
        "unknown_domain_count": cleaned.unknown_domain_count,
        "operational_domain_excluded_count": cleaned.operational_domain_excluded_count,
    }
    outputs = {
        "clean_context_source_panel": artifact(
            "clean-context-source-panel",
            cleaned.context_rows,
            config,
            no_trade_signal=True,
            available_at_preserved=all(
                bool(row.get("available_at")) for row in cleaned.context_rows
            ),
            duplicate_count=cleaned.context_duplicate_count,
            accepted_count=len(cleaned.context_rows),
            **common_metrics,
        ),
        "clean_document_panel": artifact(
            "clean-document-panel",
            cleaned.document_rows,
            config,
            document_available_at_present=all(
                bool(row.get("available_at")) for row in cleaned.document_rows
            ),
            no_trade_signal=True,
            duplicate_count=cleaned.document_duplicate_count,
            accepted_count=len(cleaned.document_rows),
            **common_metrics,
        ),
        "clean_event_reference_panel": artifact(
            "clean-event-reference-panel",
            cleaned.event_rows,
            config,
            no_trade_signal=True,
            available_at_preserved=all(
                bool(row.get("available_at")) for row in cleaned.event_rows
            ),
            duplicate_count=cleaned.event_duplicate_count,
            accepted_count=len(cleaned.event_rows),
            **common_metrics,
        ),
    }

    return {
        "module_id": MODULE_ID,
        "module_name": MODULE_NAME,
        "phase": PHASE,
        "subphase": SUBPHASE,
        "contract": CONTRACT,
        "required_inputs": required,
        "outputs": outputs,
    }
