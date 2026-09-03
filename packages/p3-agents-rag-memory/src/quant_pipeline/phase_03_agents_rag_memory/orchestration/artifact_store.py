"""Canonical in-process artifact store for Contract Pack V2 boundaries.

The store is intentionally small: it persists immutable JSON payloads by
``ArtifactPointer`` and verifies hashes on every read. Production adapters may
replace it with file/object-store implementations without changing contracts.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..contracts import ArtifactPointer, ContractModel, content_hash


@dataclass(slots=True)
class CanonicalArtifactStore:
    """Hash-verifying immutable JSON store used by the integrated boundary."""

    _payloads: dict[str, dict[str, Any]] = field(default_factory=dict)

    def put(self, pointer: ArtifactPointer, value: ContractModel | Mapping[str, Any]) -> None:
        payload = (
            value.model_dump(mode="json")
            if isinstance(value, ContractModel)
            else dict(value)
        )
        computed = content_hash(payload)
        declared = payload.get("content_hash")
        valid_hashes = {computed}
        if isinstance(declared, str):
            valid_hashes.add(declared)
        if pointer.content_hash not in valid_hashes:
            raise ValueError(
                f"artifact {pointer.artifact_id} hash mismatch: "
                f"pointer={pointer.content_hash}, computed={computed}, declared={declared}"
            )
        prior = self._payloads.get(pointer.artifact_id)
        if prior is not None and prior != payload:
            raise ValueError(f"immutable artifact collision: {pointer.artifact_id}")
        self._payloads[pointer.artifact_id] = payload

    def get(self, pointer: ArtifactPointer) -> dict[str, Any]:
        try:
            payload = self._payloads[pointer.artifact_id]
        except KeyError as exc:
            raise KeyError(f"artifact not available: {pointer.artifact_id}") from exc
        computed = content_hash(payload)
        declared = payload.get("content_hash")
        valid_hashes = {computed}
        if isinstance(declared, str):
            valid_hashes.add(declared)
        if pointer.content_hash not in valid_hashes:
            raise ValueError(f"stored artifact hash mismatch: {pointer.artifact_id}")
        return dict(payload)

    def contains(self, pointer: ArtifactPointer) -> bool:
        return pointer.artifact_id in self._payloads
