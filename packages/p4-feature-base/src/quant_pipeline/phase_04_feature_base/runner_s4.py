from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .modules.P4_S4_M01_price_return_observations import run_module as run_m01
from .modules.P4_S4_M02_volume_liquidity_microstructure_observations import run_module as run_m02
from .modules.P4_S4_M03_realized_risk_tail_observations import run_module as run_m03
from .modules.P4_S4_M04_benchmark_cross_asset_observations import run_module as run_m04
from .modules.P4_S4_M05_underlying_option_state_observations import run_module as run_m05
from .modules.P4_S4_M06_macro_event_calendar_observations import run_module as run_m06
from .modules.P4_S4_M07_social_evidence_context_observations import run_module as run_m07
from .modules.P4_S4_M08_fundamental_accounting_quality_observations import run_module as run_m08

MODULE_RUNNERS = (run_m01, run_m02, run_m03, run_m04, run_m05, run_m06, run_m07, run_m08)


def run_subphase_s4(inputs: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    outputs: dict[str, Any] = {}
    module_results: list[dict[str, Any]] = []
    for runner in MODULE_RUNNERS:
        result = runner(inputs, config)
        module_results.append(result)
        for artifact_name, artifact in result["outputs"].items():
            if artifact_name in outputs:
                raise ValueError(f"duplicate S4 output producer: {artifact_name}")
            outputs[artifact_name] = artifact
    return {
        "phase_id": "P4",
        "subphase_id": "P4.S4",
        "module_results": module_results,
        "outputs": outputs,
    }
