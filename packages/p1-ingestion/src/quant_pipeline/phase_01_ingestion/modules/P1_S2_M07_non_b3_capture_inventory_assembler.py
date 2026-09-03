from __future__ import annotations

from ._p1_semantic_helpers import merge_raw_inventories, validate_inputs


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    required = ["macro_raw_capture_inventory", "benchmark_raw_capture_inventory", "crypto_raw_capture_inventory", "document_raw_capture_inventory"]
    validate_inputs(inputs, required)
    return {"module_id": "P1.S2.M07", "module_name": "non_b3_capture_inventory_assembler", "phase": "phase_01_ingestion", "subphase": "P1.S2", "contract": "P1_S2_M07_non_b3_capture_inventory_assembler.yaml", "required_inputs": required, "outputs": {"non_b3_raw_capture_inventory": merge_raw_inventories("non_b3_raw_capture_inventory", [inputs[name] for name in required], config)}}
