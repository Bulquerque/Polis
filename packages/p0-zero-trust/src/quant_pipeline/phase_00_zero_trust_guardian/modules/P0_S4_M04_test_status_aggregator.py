from __future__ import annotations

from ._module_executor import ContractValidationError, PIPELINE_VERSION
from ._p0_s4_status import build_test_outputs, independent_control, phase_test_states
from ._p0_s4_test_evidence import (
    artifact,
    created_at,
    digest,
    envelope,
    require_call,
    validate_output,
)


INPUTS = ["collected_test_reports", "contract_test_report", "schema_test_report"]


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = require_call(inputs, config, INPUTS)
    collected = artifact(inputs["collected_test_reports"], "collected_test_reports")
    contract = artifact(inputs["contract_test_report"], "contract_test_report")
    schema = artifact(inputs["schema_test_report"], "schema_test_report")
    sources = (collected, contract, schema)
    if not all(isinstance(item.get("lineage_id"), str) for item in sources):
        raise ContractValidationError("source reports lack lineage")

    phases = phase_test_states(collected)
    controls = [
        independent_control("P0_CONTRACT_ORACLE", contract),
        independent_control("P0_SCHEMA_ORACLE", schema),
    ]
    fingerprint = digest(
        {"collected": collected.get("lineage_id"), "controls": controls, "phases": phases}
    )
    common = {
        "created_at": created_at(config),
        "pipeline_version": PIPELINE_VERSION,
        "lineage_id": f"sha256:{fingerprint}",
    }
    global_report, panel = build_test_outputs(
        phases,
        controls,
        common,
        fingerprint,
        [item["lineage_id"] for item in sources],
    )
    validate_output(global_report, "global_test_report.schema.yaml")
    validate_output(panel, "phase_test_status_panel.schema.yaml")
    return envelope(
        "P0.S4.M04",
        "test_status_aggregator",
        INPUTS,
        {"global_test_report": global_report, "phase_test_status_panel": panel},
    )
