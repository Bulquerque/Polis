from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..subphases.s4.binding import MODULE_ID, compile_scoring_bindings
from ._wire import execute_module


def run_module(inputs: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    return execute_module(MODULE_ID, compile_scoring_bindings, inputs, config)
