from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..atomic import risk
from ..economic_models import ExecutionStatus
from ..module_runtime import execute_atomic_module


def run_module(inputs: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    return execute_atomic_module(
        inputs=inputs,
        config=config,
        module_id="P4.S4.M03",
        artifact_name="risk_tail_atomic_panel",
        supported_observers=risk.SUPPORTED_OBSERVERS,
        compute=risk.compute,
        empty_data_status=ExecutionStatus.DEGRADED,
    )
