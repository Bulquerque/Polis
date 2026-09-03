from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from ..perspective_runtime import execute_perspective_module
from ..perspectives.reversion import SUPPORTED_OBSERVERS, compute
MODULE_ID="P4.S5.M02"
ARTIFACT_NAME="reversion_relative_value_perspective_panel"
REQUIRED_PANELS=('price_return_atomic_panel', 'benchmark_cross_asset_atomic_panel')

def run_module(inputs:Mapping[str,Any],config:Mapping[str,Any]) -> dict[str,Any]:
    return execute_perspective_module(inputs=inputs,config=config,module_id=MODULE_ID,artifact_name=ARTIFACT_NAME,required_panels=REQUIRED_PANELS,supported_observers=SUPPORTED_OBSERVERS,compute=compute)
