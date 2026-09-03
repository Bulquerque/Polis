from __future__ import annotations

from ._p1_semantic_helpers import raw_inventory, validate_inputs


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}; validate_inputs(inputs, ["capture_task_manifest"])
    return {"module_id": "P1.S2.M03", "module_name": "macro_raw_fetcher", "phase": "phase_01_ingestion", "subphase": "P1.S2", "contract": "P1_S2_M03_macro_raw_fetcher.yaml", "required_inputs": ["capture_task_manifest"], "outputs": {"macro_raw_capture_inventory": raw_inventory("macro_raw_capture_inventory", inputs, config, source_categories={"macro"})}}
