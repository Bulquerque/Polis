from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..subphases.s3.pareto import MODULE_ID, build_pareto_frontiers
from ._wire import execute_module


def run_module(inputs: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    return execute_module(MODULE_ID, build_pareto_frontiers, inputs, config)
