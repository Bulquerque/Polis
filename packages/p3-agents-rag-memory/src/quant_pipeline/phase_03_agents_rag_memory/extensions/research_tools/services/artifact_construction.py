"""Small construction helpers shared by S32 builders."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

from pydantic import BaseModel

from ..contracts.artifacts import ResearchToolLineage
from ..core.hashing import content_hash, stable_artifact_id
from ..core.models import ResearchToolModel

ArtifactT = TypeVar("ArtifactT", bound=ResearchToolModel)


def python_value(value: object) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python")
    return value


def as_mapping(value: object, label: str) -> Mapping[str, Any]:
    raw = python_value(value)
    if not isinstance(raw, Mapping):
        raise TypeError(f"{label} must be a mapping or Pydantic model")
    return raw


def input_hashes(values: Sequence[object]) -> tuple[str, ...]:
    return tuple(sorted(content_hash(python_value(value)) for value in values))


def lineage(module_id: str, version: str, inputs: Sequence[object]) -> ResearchToolLineage:
    return ResearchToolLineage(
        producer_module_id=module_id,
        input_hashes=input_hashes(inputs),
        configuration_hashes=(),
        code_version=version,
    )


def finalize(model: type[ArtifactT], payload: dict[str, Any]) -> ArtifactT:
    schema_id = str(payload.get("schema_id") or model.model_fields["schema_id"].default)
    hashed_payload = dict(payload)
    hashed_payload.pop("artifact_id", None)
    hashed_payload.pop("content_hash", None)
    digest = content_hash(hashed_payload)
    return model.model_validate(
        {
            **payload,
            "artifact_id": stable_artifact_id(schema_id, digest),
            "content_hash": digest,
        }
    )
