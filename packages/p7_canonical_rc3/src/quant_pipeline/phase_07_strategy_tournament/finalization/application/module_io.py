"""Module-level parsing and artifact output helpers."""
from __future__ import annotations

from typing import Mapping, TypeVar

from pydantic import BaseModel, ValidationError

from ..artifacts import validate_artifact_integrity
from ..boundary.base import ArtifactEnvelope
from ..errors import ContractViolation, ErrorContext

T = TypeVar("T", bound=BaseModel)


def parse_envelope(inputs: Mapping[str, object], name: str, module_id: str) -> ArtifactEnvelope:
    if name not in inputs:
        raise ContractViolation("P7_INPUT_ARTIFACT_MISSING", name, ErrorContext(module_id))
    try:
        envelope = ArtifactEnvelope.model_validate(inputs[name])
    except ValidationError as exc:
        raise ContractViolation("P7_ARTIFACT_SCHEMA_INVALID", f"{name}: {exc}", ErrorContext(module_id)) from exc
    validate_artifact_integrity(envelope, module_id)
    return envelope


def parse_records(envelope: ArtifactEnvelope, model: type[T], module_id: str) -> tuple[T, ...]:
    try:
        return tuple(model.model_validate(record) for record in envelope.records)
    except ValidationError as exc:
        raise ContractViolation("P7_RECORD_SCHEMA_INVALID", f"{envelope.artifact_name}: {exc}", ErrorContext(module_id)) from exc
