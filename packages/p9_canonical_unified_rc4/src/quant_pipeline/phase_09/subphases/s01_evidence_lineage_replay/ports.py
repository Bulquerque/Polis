from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ArtifactStoreReadPort(Protocol):
    def read_bytes(self, location: str) -> bytes:
        """Returns immutable bytes for a content location or raises a typed error."""


class ArtifactStoreWritePort(Protocol):
    def write_bytes(self, key: str, payload: bytes) -> str:
        """Writes bytes atomically and returns a stable location."""


class ArtifactStoreError(RuntimeError):
    pass


class InMemoryArtifactStore(ArtifactStoreReadPort, ArtifactStoreWritePort):
    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    def write_bytes(self, key: str, payload: bytes) -> str:
        location = f"mem://{key}"
        self._objects[location] = bytes(payload)
        return location

    def read_bytes(self, location: str) -> bytes:
        try:
            return self._objects[location]
        except KeyError as exc:
            raise ArtifactStoreError(f"artifact not found: {location}") from exc


class FileArtifactStore(ArtifactStoreReadPort, ArtifactStoreWritePort):
    """Filesystem adapter confined to one root; absolute and traversal paths are rejected."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, location: str) -> Path:
        relative = Path(location)
        if relative.is_absolute() or ".." in relative.parts:
            raise ArtifactStoreError("artifact location escapes configured root")
        resolved = (self._root / relative).resolve()
        if self._root not in resolved.parents and resolved != self._root:
            raise ArtifactStoreError("artifact location escapes configured root")
        return resolved

    def write_bytes(self, key: str, payload: bytes) -> str:
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(payload)
        temporary.replace(target)
        return key

    def read_bytes(self, location: str) -> bytes:
        target = self._resolve(location)
        if not target.is_file():
            raise ArtifactStoreError(f"artifact not found: {location}")
        return target.read_bytes()
