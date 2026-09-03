from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from .models import (
    RobustnessStressBundleManifest,
    CapacityRequest,
    CapacityResult,
    ConditionalEVTResult,
    DistributionalRobustnessResult,
    DRORequest,
    EVTRequest,
    HistoricalCrisisReplayResult,
    HistoricalReplayRequest,
    ReverseStressRequest,
    ReverseStressResult,
    S6OutputBundle,
    S6RunRequest,
    ScenarioRegistryRequest,
    SensitivitySurfaceRequest,
    SensitivitySurfaceResult,
    StressModelValidationResult,
    StressScenarioRegistrySnapshot,
    StressValidationRequest,
)

SCHEMA_MODELS: tuple[type[BaseModel], ...] = (
    ScenarioRegistryRequest,
    StressScenarioRegistrySnapshot,
    HistoricalReplayRequest,
    HistoricalCrisisReplayResult,
    SensitivitySurfaceRequest,
    SensitivitySurfaceResult,
    EVTRequest,
    ConditionalEVTResult,
    DRORequest,
    DistributionalRobustnessResult,
    CapacityRequest,
    CapacityResult,
    ReverseStressRequest,
    ReverseStressResult,
    StressValidationRequest,
    StressModelValidationResult,
    S6RunRequest,
    S6OutputBundle,
    RobustnessStressBundleManifest,
)


def export_schemas(output_directory: Path) -> tuple[Path, ...]:
    output_directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for model in SCHEMA_MODELS:
        path = output_directory / f"{model.__name__}.schema.json"
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n")
        written.append(path)
    return tuple(written)
