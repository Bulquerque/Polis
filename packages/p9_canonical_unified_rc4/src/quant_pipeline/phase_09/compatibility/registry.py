from __future__ import annotations

import json
from importlib.resources import files
from typing import Any


def load_cross_phase_compatibility_matrix() -> dict[str, Any]:
    resource = files("quant_pipeline.phase_09.compatibility.resources").joinpath(
        "cross_phase_compatibility_matrix.json"
    )
    value = json.loads(resource.read_text(encoding="utf-8"))
    ids = [item["phase_id"] for item in value["entries"]]
    if ids != [f"P{index}" for index in range(9)]:
        raise ValueError("packaged compatibility matrix does not cover P0 through P8")
    return value
