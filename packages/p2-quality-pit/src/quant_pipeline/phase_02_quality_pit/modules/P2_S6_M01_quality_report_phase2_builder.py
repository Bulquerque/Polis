from __future__ import annotations

from ..s6_quality import PHASE2_PANELS, evaluate_phase2_quality
from ._p2_semantic_helpers import meta, require_inputs


def run_module(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    required = list(PHASE2_PANELS)
    require_inputs(inputs, required)

    evaluation = evaluate_phase2_quality(inputs, config)
    report = {
        **meta("quality-report-phase-2", evaluation, config),
        "schema_version": "quality-report-phase-2.v1",
        **evaluation,
    }

    return {
        "module_id": "P2.S6.M01",
        "module_name": "quality_report_phase2_builder",
        "phase": "phase_02_quality_pit",
        "subphase": "P2.S6",
        "contract": "P2_S6_M01_quality_report_phase2_builder.yaml",
        "required_inputs": required,
        "outputs": {"quality_report_phase_2": report},
    }
