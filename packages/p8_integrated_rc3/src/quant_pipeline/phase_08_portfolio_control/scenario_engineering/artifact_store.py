"""Explicit filesystem artifact writer used by the public API and CLI."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from .arrays import ScenarioSet, StressScenarioSet


class ArtifactWriter:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def write_scenario_set(self, name: str, scenarios: ScenarioSet) -> str:
        path = self.root / f"{name}.npz"
        scenarios.save_npz(path)
        return path.name

    def write_stress_set(self, name: str, stresses: StressScenarioSet) -> str:
        path = self.root / f"{name}.npz"
        import numpy as np
        np.savez_compressed(
            path, values=stresses.values, stress_ids=np.asarray(stresses.stress_ids),
            factor_ids=np.asarray(stresses.factor_ids), step_labels=np.asarray(stresses.step_labels),
            severities=np.asarray(stresses.severities), tags=np.asarray(["|".join(x) for x in stresses.tags]),
        )
        return path.name

    def write_model(self, name: str, model: BaseModel) -> str:
        path = self.root / f"{name}.json"
        path.write_text(json.dumps(model.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")
        return path.name
