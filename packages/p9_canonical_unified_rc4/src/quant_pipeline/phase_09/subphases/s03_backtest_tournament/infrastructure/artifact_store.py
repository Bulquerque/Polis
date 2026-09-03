"""Atomic local content-addressed artifact storage."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path

from ..common import Sha256


class LocalArtifactStore:
    """Write immutable byte payloads using temp-file + atomic replace."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, digest: str) -> Path:
        return self.root / digest[:2] / digest[2:]

    def put(self, digest: str, payload: bytes) -> Path:
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError("digest must be lowercase SHA-256 hex")
        observed = hashlib.sha256(payload).hexdigest()
        if observed != digest:
            raise ValueError("digest does not match payload")
        destination = self.path_for(digest)
        if destination.exists():
            existing = destination.read_bytes()
            if existing != payload:
                raise ValueError("content hash collision or corrupted store")
            return destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temp_name = tempfile.mkstemp(dir=destination.parent, prefix=".staging-")
        try:
            with os.fdopen(file_descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, destination)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return destination

    def get(self, digest: str) -> bytes:
        return self.path_for(digest).read_bytes()
