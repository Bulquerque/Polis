from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from ..perspective_runtime import execute_perspective_module
from ..perspectives.carry import SUPPORTED_OBSERVERS, compute
MODULE_ID="P4.S5.M10"
ARTIFACT_NAME="carry_curve_basis_perspective_panel"
REQUIRED_PANELS=('macro_event_calendar_atomic_panel', 'underlying_option_state_atomic_panel')

def run_module(inputs:Mapping[str,Any],config:Mapping[str,Any]) -> dict[str,Any]:
    return execute_perspective_module(inputs=inputs,config=config,module_id=MODULE_ID,artifact_name=ARTIFACT_NAME,required_panels=REQUIRED_PANELS,supported_observers=SUPPORTED_OBSERVERS,compute=compute)
