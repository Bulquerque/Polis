from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from ..perspective_runtime import execute_perspective_module
from ..perspectives.liquidity import SUPPORTED_OBSERVERS, compute
MODULE_ID="P4.S5.M04"
ARTIFACT_NAME="liquidity_attention_crowding_perspective_panel"
REQUIRED_PANELS=('liquidity_microstructure_atomic_panel', 'underlying_option_state_atomic_panel', 'social_evidence_context_atomic_panel')

def run_module(inputs:Mapping[str,Any],config:Mapping[str,Any]) -> dict[str,Any]:
    return execute_perspective_module(inputs=inputs,config=config,module_id=MODULE_ID,artifact_name=ARTIFACT_NAME,required_panels=REQUIRED_PANELS,supported_observers=SUPPORTED_OBSERVERS,compute=compute)
