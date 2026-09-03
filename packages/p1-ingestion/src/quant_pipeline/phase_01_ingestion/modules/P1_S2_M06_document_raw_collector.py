from __future__ import annotations

from ._p1_semantic_helpers import raw_inventory, validate_inputs


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}; validate_inputs(inputs, ["capture_task_manifest"])
    return {"module_id": "P1.S2.M06", "module_name": "document_raw_collector", "phase": "phase_01_ingestion", "subphase": "P1.S2", "contract": "P1_S2_M06_document_raw_collector.yaml", "required_inputs": ["capture_task_manifest"], "outputs": {"document_raw_capture_inventory": raw_inventory("document_raw_capture_inventory", inputs, config, text_allowed=True, source_categories={"document"})}}
