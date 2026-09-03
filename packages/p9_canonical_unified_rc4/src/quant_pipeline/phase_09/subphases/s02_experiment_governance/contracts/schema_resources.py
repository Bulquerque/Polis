from __future__ import annotations

import json
from importlib.resources import files

PACKAGE = "quant_pipeline.phase_09.subphases.s02_experiment_governance.generated_schemas"


def list_schema_names() -> tuple[str, ...]:
    root = files(PACKAGE)
    return tuple(sorted(item.name for item in root.iterdir() if item.name.endswith(".json")))


def read_schema(name: str) -> dict[str, object]:
    if "/" in name or "\\" in name or not name.endswith(".json"):
        raise ValueError("schema name must be a plain JSON filename")
    raw = files(PACKAGE).joinpath(name).read_text(encoding="utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("schema resource must contain a JSON object")
    return value
