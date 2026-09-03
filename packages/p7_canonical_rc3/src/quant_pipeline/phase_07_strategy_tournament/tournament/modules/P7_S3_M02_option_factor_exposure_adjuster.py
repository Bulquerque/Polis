from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..subphases.s3.factors import MODULE_ID, adjust_factor_exposure
from ._wire import execute_module


def run_module(inputs: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    return execute_module(MODULE_ID, adjust_factor_exposure, inputs, config)
