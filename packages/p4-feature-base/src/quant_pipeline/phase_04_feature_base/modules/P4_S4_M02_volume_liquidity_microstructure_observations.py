from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..atomic import liquidity
from ..economic_models import ExecutionStatus
from ..module_runtime import execute_atomic_module


def run_module(inputs: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    return execute_atomic_module(
        inputs=inputs,
        config=config,
        module_id="P4.S4.M02",
        artifact_name="liquidity_microstructure_atomic_panel",
        supported_observers=liquidity.SUPPORTED_OBSERVERS,
        compute=liquidity.compute,
        empty_data_status=ExecutionStatus.DEGRADED,
    )
