"""Read-only access to generated contract schemas bundled in the wheel."""

from __future__ import annotations

import json
from importlib.resources import files

SCHEMA_PACKAGE = "quant_pipeline.phase_09.generated_schemas"


def list_schema_names() -> tuple[str, ...]:
    root = files(SCHEMA_PACKAGE)
    return tuple(sorted(item.name for item in root.iterdir() if item.name.endswith(".json")))


def read_schema(name: str) -> dict[str, object]:
    if "/" in name or "\\" in name or not name.endswith(".json"):
        raise ValueError("schema name must be a simple JSON filename")
    resource = files(SCHEMA_PACKAGE).joinpath(name)
    if not resource.is_file():
        raise FileNotFoundError(name)
    value = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("schema resource must contain a JSON object")
    return value
