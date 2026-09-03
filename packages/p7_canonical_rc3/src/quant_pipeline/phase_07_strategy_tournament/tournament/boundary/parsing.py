from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any, TypeVar

from pydantic import BaseModel, TypeAdapter, ValidationError

from .artifacts import ArtifactEnvelope
from ..domain.errors import ContractViolation, IntegrityViolation
from ..domain.reasoning import reason_prefix

RecordT = TypeVar("RecordT", bound=BaseModel)


def parse_artifact(
    payload: Any,
    record_type: type[RecordT],
    *,
    expected_name: str,
    module_id: str,
    strict_hash_validation: bool,
) -> ArtifactEnvelope[RecordT]:
    prefix = reason_prefix(module_id)
    try:
        adapter = TypeAdapter(ArtifactEnvelope[record_type])
        artifact = adapter.validate_json(json.dumps(payload, allow_nan=False, sort_keys=True))
    except (ValidationError, ValueError, TypeError) as exc:
        details: dict[str, Any] = {"error": str(exc)}
        if isinstance(exc, ValidationError):
            details = {"errors": exc.errors(include_url=False)}
        raise ContractViolation(
            f"{prefix}_INPUT_SCHEMA_INVALID",
            f"invalid artifact {expected_name}",
            module_id=module_id,
            details=details,
        ) from exc
    if artifact.artifact_name != expected_name:
        raise ContractViolation(
            f"{prefix}_ARTIFACT_NAME_MISMATCH",
            f"expected {expected_name}, received {artifact.artifact_name}",
            module_id=module_id,
        )
    if strict_hash_validation and artifact.calculated_hash() != artifact.content_sha256:
        raise IntegrityViolation(
            f"{prefix}_CONTENT_HASH_MISMATCH",
            f"content hash mismatch for {expected_name}",
            module_id=module_id,
            details={"artifact_id": artifact.artifact_id},
        )
    return artifact


def require_inputs(inputs: Mapping[str, Any], names: tuple[str, ...], module_id: str) -> None:
    missing = sorted(set(names) - set(inputs))
    if missing:
        raise ContractViolation(
            f"{reason_prefix(module_id)}_REQUIRED_INPUT_MISSING",
            "required module inputs are missing",
            module_id=module_id,
            details={"missing": missing},
        )
