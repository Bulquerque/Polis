from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from pydantic import ValidationError

from .economic_errors import ContractError
from .fusion_models import AlignedPerspectivePanel, InteractionFeaturePanel, PerspectiveConflictPanel
from .fusion_validation import prepare_s6_inputs
from .modules.P4_S6_M01_multi_view_alignment import run_module as run_m01
from .modules.P4_S6_M02_confirmation_conflict_engine import run_module as run_m02
from .modules.P4_S6_M03_hypothesis_constrained_interaction_builder import run_module as run_m03
from .modules.P4_S6_M04_multi_horizon_missing_view_assembler import run_module as run_m04


def _inject(prepared:dict[str,Any],result:dict[str,Any]) -> None:
    for name,raw in result["outputs"].items():
        if name in prepared: raise ContractError("P4_S6_DUPLICATE_OUTPUT",f"duplicate output: {name}")
        try:
            if name=="aligned_perspective_panel": prepared[name]=AlignedPerspectivePanel.model_validate(raw)
            elif name=="perspective_conflict_panel": prepared[name]=PerspectiveConflictPanel.model_validate(raw)
            elif name=="interaction_feature_panel": prepared[name]=InteractionFeaturePanel.model_validate(raw)
            else: prepared[name]=raw
        except ValidationError as exc:
            raise ContractError("P4_S6_OUTPUT_SCHEMA_INVALID",f"invalid module output: {name}",details={"errors":exc.errors(include_url=False)}) from exc


def run_subphase_s6(inputs:Mapping[str,Any],config:Mapping[str,Any]) -> dict[str,Any]:
    prepared=prepare_s6_inputs(inputs,config); results=[]; outputs={}
    for runner in (run_m01,run_m02,run_m03,run_m04):
        result=runner(prepared,config); results.append(result)
        for name,value in result["outputs"].items():
            if name in outputs: raise ContractError("P4_S6_DUPLICATE_OUTPUT",f"duplicate output: {name}")
            outputs[name]=value
        _inject(prepared,result)
    return {"phase_id":"P4","subphase_id":"P4.S6","module_results":results,"outputs":outputs}
