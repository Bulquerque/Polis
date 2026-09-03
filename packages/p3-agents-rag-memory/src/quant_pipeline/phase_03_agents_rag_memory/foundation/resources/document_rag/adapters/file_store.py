from __future__ import annotations

import os
from pathlib import Path
import tempfile

from ..canonical import sha256_bytes
from ..errors import ErrorCategory, PersistenceFailureError, error
from ..models import ArtifactRef


class FileArtifactStore:
    """Content-addressed local store with atomic publication."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def put_bytes(
        self,
        *,
        artifact_type: str,
        content: bytes,
        media_type: str,
        suffix: str,
        record_count: int | None,
        format_version: str,
    ) -> ArtifactRef:
        digest = sha256_bytes(content)
        directory = self._root / artifact_type / digest
        target = directory / f"data{suffix}"
        directory.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            try:
                with tempfile.NamedTemporaryFile(dir=directory, delete=False) as handle:
                    temp_path = Path(handle.name)
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_path, target)
            except OSError as exc:
                raise PersistenceFailureError(
                    error(
                        "P3_S12_M01_INDEX_PERSISTENCE_FAILURE",
                        ErrorCategory.PERSISTENCE,
                        "failed to atomically persist an S12 artifact",
                        context={"artifact_type": artifact_type},
                    )
                ) from exc
        return ArtifactRef(
            artifact_type=artifact_type,
            uri=target.as_uri(),
            content_hash=digest,
            media_type=media_type,
            size_bytes=len(content),
            record_count=record_count,
            format_version=format_version,
        )

    def get_bytes(self, reference: ArtifactRef) -> bytes:
        path = Path(reference.uri.removeprefix("file://"))
        content = path.read_bytes()
        if sha256_bytes(content) != reference.content_hash:
            raise PersistenceFailureError(
                error(
                    "P3_S12_M02_ARTIFACT_HASH_MISMATCH",
                    ErrorCategory.PERSISTENCE,
                    "persisted artifact hash does not match its reference",
                    context={"artifact_type": reference.artifact_type},
                )
            )
        return content
