from __future__ import annotations

import json
from pathlib import Path

from .contracts import RobustnessStressOutputBundle, RobustnessStressRunRequest


MODELS = (RobustnessStressRunRequest, RobustnessStressOutputBundle)


def export_schemas(destination: Path) -> tuple[Path, ...]:
    destination.mkdir(parents=True, exist_ok=True)
    paths = []
    for model in MODELS:
        path = destination / f"{model.__name__}.schema.json"
        path.write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        paths.append(path)
    return tuple(paths)
