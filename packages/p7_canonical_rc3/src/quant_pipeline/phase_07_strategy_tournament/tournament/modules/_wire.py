from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable

from ..boundary.artifacts import ArtifactEnvelope
from ..boundary.requests import ModuleExecutionConfig

Service = Callable[[Mapping[str, Any], ModuleExecutionConfig], dict[str, ArtifactEnvelope[Any]]]


def execute_module(
    module_id: str,
    service: Service,
    inputs: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    execution_config = ModuleExecutionConfig.from_mapping(config)
    outputs = service(inputs, execution_config)
    return {
        "module_id": module_id,
        "status": "PASS",
        "outputs": {name: artifact.model_dump(mode="json") for name, artifact in outputs.items()},
        "output_artifact_ids": {name: artifact.artifact_id for name, artifact in outputs.items()},
    }
