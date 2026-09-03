from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Mapping

from pydantic import JsonValue

from ..errors import BoundaryValidationError
from ..identity import stable_id
from ..contracts_internal import ArtifactPointer, ExecutionStatus, content_hash
from .models import ArtifactWriteRequest, JsonPayload


class FileJsonArtifactRepository:
    """Immutable, hash-verifying JSON repository with atomic writes."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    async def read_json(self, pointer: ArtifactPointer) -> JsonPayload:
        path = self._safe_path(pointer.storage_ref)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BoundaryValidationError(f"cannot read artifact {pointer.artifact_id}: {exc}") from exc
        if not isinstance(raw, dict):
            raise BoundaryValidationError(f"artifact {pointer.artifact_id} is not a JSON object")
        payload = self._json_object(raw)
        if content_hash(payload) != pointer.content_hash:
            raise BoundaryValidationError(f"artifact hash mismatch: {pointer.artifact_id}")
        return payload

    async def write_json(self, request: ArtifactWriteRequest) -> ArtifactPointer:
        payload = dict(request.payload)
        try:
            digest = content_hash(payload)
        except (TypeError, ValueError) as exc:
            raise BoundaryValidationError(
                f"artifact {request.artifact_name} is not canonical JSON: {exc}"
            ) from exc
        artifact_id = str(payload.get("artifact_id") or stable_id(
            "runtime-artifact", request.producer_module_id, request.artifact_name, digest
        ))
        relative = Path(request.producer_module_id.replace(".", "_")) / f"{artifact_id}.json"
        destination = (self._root / relative).resolve()
        if self._root not in destination.parents:
            raise BoundaryValidationError("artifact path escaped repository root")
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            serialized = json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise BoundaryValidationError(
                f"artifact {artifact_id} is not canonical JSON: {exc}"
            ) from exc
        if destination.exists():
            if destination.read_text(encoding="utf-8") != serialized:
                raise BoundaryValidationError(f"immutable artifact collision: {artifact_id}")
        else:
            fd, temp_name = tempfile.mkstemp(prefix=".write-", dir=destination.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(serialized)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_name, destination)
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
        records = payload.get("records")
        items = payload.get("items")
        row_count = len(records) if isinstance(records, list) else len(items) if isinstance(items, list) else None
        raw_status = str(payload.get("status", "READY"))
        status_map = {
            "PASS": ExecutionStatus.READY,
            "READY": ExecutionStatus.READY,
            "EMPTY_VALID": ExecutionStatus.EMPTY_VALID,
            "DEGRADED": ExecutionStatus.DEGRADED,
            "BLOCKED": ExecutionStatus.BLOCKED,
            "FAILED": ExecutionStatus.FAILED,
            "SKIPPED_NOT_APPLICABLE": ExecutionStatus.SKIPPED_NOT_APPLICABLE,
        }
        try:
            status = status_map[raw_status]
        except KeyError as exc:
            raise BoundaryValidationError(
                f"artifact {artifact_id} has unknown status {raw_status!r}"
            ) from exc
        return ArtifactPointer(
            artifact_name=request.artifact_name,
            schema_id=request.schema_id,
            schema_version=request.schema_version,
            artifact_id=artifact_id,
            content_hash=digest,
            storage_ref=relative.as_posix(),
            producer_module_id=request.producer_module_id,
            status=status,
            row_count=row_count,
            grain=(),
            lineage_id=request.lineage_id,
        )

    def _safe_path(self, storage_ref: str) -> Path:
        ref = Path(storage_ref)
        if ref.is_absolute() or ".." in ref.parts:
            raise BoundaryValidationError("unsafe artifact storage_ref")
        path = (self._root / ref).resolve()
        if path != self._root and self._root not in path.parents:
            raise BoundaryValidationError("artifact storage_ref escaped repository root")
        return path

    @classmethod
    def _json_object(cls, value: Mapping[object, object]) -> JsonPayload:
        result: JsonPayload = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise BoundaryValidationError("artifact JSON object contains a non-string key")
            result[key] = cls._json_value(item)
        return result

    @classmethod
    def _json_value(cls, value: object) -> JsonValue:
        if value is None or isinstance(value, (str, int, bool)):
            return value
        if isinstance(value, float):
            if not math.isfinite(value):
                raise BoundaryValidationError("artifact contains a non-finite float")
            return value
        if isinstance(value, Mapping):
            return cls._json_object(value)
        if isinstance(value, list):
            return [cls._json_value(item) for item in value]
        raise BoundaryValidationError(f"artifact contains non-JSON value {type(value).__name__}")


class InMemoryJsonArtifactRepository:
    """Immutable in-memory repository for deterministic qualification runs."""

    def __init__(self, initial: Mapping[str, tuple[ArtifactPointer, Mapping[str, object]]] | None = None) -> None:
        self._artifacts: dict[str, tuple[ArtifactPointer, JsonPayload]] = {}
        for artifact_id, (pointer, payload) in (initial or {}).items():
            normalized = FileJsonArtifactRepository._json_object(payload)
            self._artifacts[str(artifact_id)] = (pointer, normalized)

    def seed(self, pointer: ArtifactPointer, payload: Mapping[str, object]) -> None:
        normalized = FileJsonArtifactRepository._json_object(payload)
        digest = content_hash(normalized)
        if digest != pointer.content_hash:
            raise BoundaryValidationError(f"seed artifact hash mismatch: {pointer.artifact_id}")
        existing = self._artifacts.get(pointer.artifact_id)
        if existing is not None and existing != (pointer, normalized):
            raise BoundaryValidationError(f"immutable seed collision: {pointer.artifact_id}")
        self._artifacts[pointer.artifact_id] = (pointer, normalized)

    async def read_json(self, pointer: ArtifactPointer) -> JsonPayload:
        try:
            stored_pointer, payload = self._artifacts[pointer.artifact_id]
        except KeyError as exc:
            raise BoundaryValidationError(f"artifact not found: {pointer.artifact_id}") from exc
        if stored_pointer != pointer:
            raise BoundaryValidationError(f"artifact pointer mismatch: {pointer.artifact_id}")
        return dict(payload)

    async def write_json(self, request: ArtifactWriteRequest) -> ArtifactPointer:
        payload = FileJsonArtifactRepository._json_object(request.payload)
        digest = content_hash(payload)
        artifact_id = str(payload.get("artifact_id") or stable_id(
            "runtime-artifact", request.producer_module_id, request.artifact_name, digest
        ))
        records = payload.get("records")
        items = payload.get("items")
        row_count = len(records) if isinstance(records, list) else len(items) if isinstance(items, list) else None
        raw_status = str(payload.get("status", "READY"))
        status_map = {
            "PASS": ExecutionStatus.READY,
            "READY": ExecutionStatus.READY,
            "EMPTY_VALID": ExecutionStatus.EMPTY_VALID,
            "DEGRADED": ExecutionStatus.DEGRADED,
            "BLOCKED": ExecutionStatus.BLOCKED,
            "FAILED": ExecutionStatus.FAILED,
            "SKIPPED_NOT_APPLICABLE": ExecutionStatus.SKIPPED_NOT_APPLICABLE,
        }
        try:
            status = status_map[raw_status]
        except KeyError as exc:
            raise BoundaryValidationError(f"artifact {artifact_id} has unknown status {raw_status!r}") from exc
        pointer = ArtifactPointer(
            artifact_name=request.artifact_name,
            schema_id=request.schema_id,
            schema_version=request.schema_version,
            artifact_id=artifact_id,
            content_hash=digest,
            storage_ref=f"memory://{request.producer_module_id}/{artifact_id}",
            producer_module_id=request.producer_module_id,
            status=status,
            row_count=row_count,
            grain=(),
            lineage_id=request.lineage_id,
        )
        existing = self._artifacts.get(artifact_id)
        if existing is not None and existing != (pointer, payload):
            raise BoundaryValidationError(f"immutable artifact collision: {artifact_id}")
        self._artifacts[artifact_id] = (pointer, payload)
        return pointer

    def snapshot(self) -> dict[str, dict[str, object]]:
        return {
            artifact_id: {
                "pointer": pointer.model_dump(mode="json"),
                "payload": dict(payload),
            }
            for artifact_id, (pointer, payload) in sorted(self._artifacts.items())
        }
