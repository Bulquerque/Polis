from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..atomic import cross_asset
from ..economic_models import ExecutionStatus
from ..module_runtime import execute_atomic_module


def run_module(inputs: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    return execute_atomic_module(
        inputs=inputs,
        config=config,
        module_id="P4.S4.M04",
        artifact_name="benchmark_cross_asset_atomic_panel",
        supported_observers=cross_asset.SUPPORTED_OBSERVERS,
        compute=cross_asset.compute,
        empty_data_status=ExecutionStatus.DEGRADED,
    )
