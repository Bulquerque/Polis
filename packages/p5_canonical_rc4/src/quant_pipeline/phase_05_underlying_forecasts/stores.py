"""Atomic content-addressed stores with containment and hash checks."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .domain.core import ArtifactReference
from .errors import ArtifactError, ArtifactIntegrityError


def _payload(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, tuple):
        return [_payload(item) for item in value]
    if isinstance(value, list):
        return [_payload(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _payload(item) for key, item in value.items()}
    return value


class JsonArtifactStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        artifact_type: str,
        value: Any,
        *,
        schema_version: str = "1.0.0",
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactReference:
        payload = _payload(value)
        raw = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        relative = Path(artifact_type) / f"{digest[:24]}.json"
        path = self._contained(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            self._atomic_write(path, raw)
        row_count = len(payload.get("records", [])) if isinstance(payload, dict) else None
        return ArtifactReference(
            artifact_id=f"{artifact_type}-{digest[:20]}",
            artifact_type=artifact_type,
            storage_uri=relative.as_posix(),
            content_hash=digest,
            schema_version=schema_version,
            row_count=row_count,
            metadata=metadata or {},
        )

    def read(self, reference: ArtifactReference) -> Any:
        path = self._contained(Path(reference.storage_uri))
        if not path.is_file():
            raise ArtifactError(f"artifact not found: {reference.storage_uri}")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != reference.content_hash:
            raise ArtifactIntegrityError("artifact hash mismatch")
        return json.loads(raw.decode("utf-8"))

    def _contained(self, relative: Path) -> Path:
        candidate = (self.root / relative).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ArtifactError("artifact path escapes configured root")
        return candidate

    @staticmethod
    def _atomic_write(path: Path, raw: bytes) -> None:
        descriptor, temporary = tempfile.mkstemp(prefix=".p5-", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
