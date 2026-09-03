"""Explicit writer for P8.S4 numerical and model artifacts."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from .arrays import DependenceArrays, GreekPathArrays, ScenarioPnLCube


class ArtifactWriter:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def write_pnl_cube(self, cube: ScenarioPnLCube) -> str:
        path = self.root / "scenario_pnl_cube.npz"
        cube.save_npz(path)
        return path.name

    def write_dependence(self, state: DependenceArrays) -> str:
        path = self.root / "dependence_state.npz"
        state.save_npz(path)
        return path.name

    def write_greek_path(self, state: GreekPathArrays) -> str:
        path = self.root / "greek_path_state.npz"
        state.save_npz(path)
        return path.name

    def write_model(self, name: str, model: BaseModel) -> str:
        path = self.root / f"{name}.json"
        path.write_text(json.dumps(model.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")
        return path.name
