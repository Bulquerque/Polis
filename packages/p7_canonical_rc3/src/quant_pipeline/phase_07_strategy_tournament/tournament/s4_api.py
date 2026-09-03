from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .s4_runner import run_subphase


def run(inputs: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    """Execute P7.S4 with explicit content-addressed artifacts."""
    return run_subphase(inputs, config)
