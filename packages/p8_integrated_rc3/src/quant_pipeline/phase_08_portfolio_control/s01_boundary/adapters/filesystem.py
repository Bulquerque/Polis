"""File-system artifact adapter keyed by artifact_id.

The adapter never searches for a 'latest' file. The caller must provide a
content-addressed reference whose artifact_id maps to an exact file name.
"""

from __future__ import annotations

from pathlib import Path

from quant_pipeline.phase_08_contracts.common import ArtifactReference

from ..errors import ExternalSystemError


class FileArtifactStore:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def read(self, reference: ArtifactReference) -> bytes:
        candidate = (self._root / reference.artifact_id).resolve()
        if self._root not in candidate.parents:
            raise ExternalSystemError("artifact path escapes configured root")
        try:
            return candidate.read_bytes()
        except OSError as exc:
            raise ExternalSystemError(f"cannot read artifact: {reference.artifact_id}") from exc
