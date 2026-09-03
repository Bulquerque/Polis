from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from .economic_errors import ContractError
from .economic_models import AtomicFeaturePanel
from .perspective_models import PerspectiveExecutionRegistry
from .modules.P4_S5_M01_momentum_trend_persistence_perspectives import run_module as run_m01
from .modules.P4_S5_M02_reversion_relative_value_perspectives import run_module as run_m02
from .modules.P4_S5_M03_risk_uncertainty_stress_perspectives import run_module as run_m03
from .modules.P4_S5_M04_liquidity_attention_crowding_perspectives import run_module as run_m04
from .modules.P4_S5_M05_structure_contagion_breadth_perspectives import run_module as run_m05
from .modules.P4_S5_M06_macro_cycle_regime_state_perspectives import run_module as run_m06
from .modules.P4_S5_M07_event_surprise_seasonality_perspectives import run_module as run_m07
from .modules.P4_S5_M08_narrative_evidence_disagreement_perspectives import run_module as run_m08
from .modules.P4_S5_M09_value_quality_profitability_investment_perspectives import run_module as run_m09
from .modules.P4_S5_M10_carry_curve_basis_perspectives import run_module as run_m10

MODULE_RUNNERS=(run_m01,run_m02,run_m03,run_m04,run_m05,run_m06,run_m07,run_m08,run_m09,run_m10)
ATOMIC_ARTIFACTS=(
    "price_return_atomic_panel","liquidity_microstructure_atomic_panel","risk_tail_atomic_panel",
    "benchmark_cross_asset_atomic_panel","underlying_option_state_atomic_panel",
    "macro_event_calendar_atomic_panel","social_evidence_context_atomic_panel",
    "fundamental_accounting_atomic_panel",
)


def _prepare_inputs(inputs: Mapping[str, Any]) -> dict[str, Any]:
    prepared=dict(inputs)
    registry=prepared.get("approved_hypothesis_passport_registry")
    try:
        if registry is not None and not isinstance(registry,PerspectiveExecutionRegistry):
            prepared["approved_hypothesis_passport_registry"]=PerspectiveExecutionRegistry.model_validate(registry)
    except ValidationError as exc:
        raise ContractError("P4_S5_SCHEMA_INVALID","S5 registry pre-validation failed",details={"errors":exc.errors(include_url=False)}) from exc
    try:
        for name in ATOMIC_ARTIFACTS:
            raw=prepared.get(name)
            if raw is not None and not isinstance(raw,AtomicFeaturePanel):
                prepared[name]=AtomicFeaturePanel.model_validate(raw)
    except ValidationError as exc:
        raise ContractError("P4_S5_ATOMIC_SCHEMA_INVALID","S5 atomic pre-validation failed",details={"errors":exc.errors(include_url=False)}) from exc
    return prepared


def run_subphase_s5(inputs: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    prepared=_prepare_inputs(inputs)
    outputs={}; results=[]
    for runner in MODULE_RUNNERS:
        result=runner(prepared,config); results.append(result)
        for name,artifact in result["outputs"].items():
            if name in outputs: raise ValueError(f"duplicate S5 output producer: {name}")
            outputs[name]=artifact
    return {"phase_id":"P4","subphase_id":"P4.S5","module_results":results,"outputs":outputs}
