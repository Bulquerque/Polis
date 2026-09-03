from __future__ import annotations

from ._p1_semantic_helpers import raw_inventory, validate_inputs


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    validate_inputs(inputs, ["capture_task_manifest"])
    return {"module_id": "P1.S2.M02", "module_name": "b3_cotahist_raw_fetcher", "phase": "phase_01_ingestion", "subphase": "P1.S2", "contract": "P1_S2_M02_b3_cotahist_raw_fetcher.yaml", "required_inputs": ["capture_task_manifest"], "outputs": {"b3_raw_capture_inventory": raw_inventory("b3_raw_capture_inventory", inputs, config, source_categories={"b3"})}}
