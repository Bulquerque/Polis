from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from ..economic_models import ExecutionContext
from ..fusion_runtime import run_horizon_assembler

MODULE_ID="P4.S6.M04"

def run_module(inputs:Mapping[str,Any],config:Mapping[str,Any]) -> dict[str,Any]:
    panel,manifest=run_horizon_assembler(inputs,ExecutionContext.model_validate(config))
    return {"module_id":MODULE_ID,"execution_status":panel.execution_status.value,"outputs":{"horizon_feature_panel":panel.model_dump(mode="json"),"horizon_feature_set_manifest":manifest.model_dump(mode="json")}}
