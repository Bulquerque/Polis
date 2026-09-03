from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from .models import (
    BacktestRobustnessQualificationReport,
    BlockBootstrapRequest,
    BlockBootstrapResult,
    BlockLengthSelectionRequest,
    BlockLengthSelectionResult,
    DependenceDiagnosticsRequest,
    DependenceDiagnosticsResult,
    HierarchicalBootstrapRequest,
    HierarchicalBootstrapResult,
    MetricDistributionRequest,
    MetricDistributionResult,
    RobustnessQualificationRequest,
    S5OutputBundle,
    S5RunRequest,
    SharpeInferenceRequest,
    SharpeInferenceResult,
    TradeResamplingRequest,
    TradeResamplingResult,
)

SCHEMA_MODELS: tuple[type[BaseModel], ...] = (
    DependenceDiagnosticsRequest,
    DependenceDiagnosticsResult,
    BlockLengthSelectionRequest,
    BlockLengthSelectionResult,
    BlockBootstrapRequest,
    BlockBootstrapResult,
    HierarchicalBootstrapRequest,
    HierarchicalBootstrapResult,
    TradeResamplingRequest,
    TradeResamplingResult,
    MetricDistributionRequest,
    MetricDistributionResult,
    SharpeInferenceRequest,
    SharpeInferenceResult,
    RobustnessQualificationRequest,
    BacktestRobustnessQualificationReport,
    S5RunRequest,
    S5OutputBundle,
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
