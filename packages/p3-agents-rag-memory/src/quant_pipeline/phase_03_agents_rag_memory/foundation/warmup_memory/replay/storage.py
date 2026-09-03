from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
from pathlib import Path

from .errors import CheckpointStoreError, S11Issue
from .models import ArtifactRef, ReplayState


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


class InMemoryCheckpointStore:
    """Deterministic checkpoint store for unit and integration tests."""

    def __init__(self) -> None:
        self._states: dict[str, ReplayState] = {}

    async def write(self, checkpoint_id: str, state: ReplayState) -> ArtifactRef:
        self._states[checkpoint_id] = state
        return ArtifactRef(
            artifact_id=checkpoint_id,
            artifact_type="cycle_state_checkpoint",
            content_hash=state.state_hash,
            schema_id="replay_state.v2",
            schema_version="2.0.0",
        )

    async def load(self, checkpoint_id: str) -> ReplayState:
        try:
            return self._states[checkpoint_id]
        except KeyError as exc:
            raise CheckpointStoreError([
                S11Issue("A3_S11_CHECKPOINT_NOT_FOUND", f"Checkpoint {checkpoint_id!r} not found")
            ]) from exc


class AtomicJsonCheckpointStore:
    """Cross-platform atomic JSON checkpoint store using same-filesystem replace."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, checkpoint_id: str) -> Path:
        if not checkpoint_id or any(part in checkpoint_id for part in ("/", "\\", "..")):
            raise CheckpointStoreError([
                S11Issue("A3_S11_CHECKPOINT_ID_INVALID", "checkpoint_id is not path-safe")
            ])
        return self._root / f"{checkpoint_id}.json"

    async def write(self, checkpoint_id: str, state: ReplayState) -> ArtifactRef:
        return await asyncio.to_thread(self._write_sync, checkpoint_id, state)

    def _write_sync(self, checkpoint_id: str, state: ReplayState) -> ArtifactRef:
        target = self._path(checkpoint_id)
        payload = canonical_json_bytes(state.model_dump(mode="json"))
        actual_hash = hashlib.sha256(payload).hexdigest()
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temp_name = handle.name
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, target)
            temp_name = None
            try:
                directory_fd = os.open(target.parent, os.O_RDONLY)
            except (AttributeError, OSError):
                directory_fd = None
            if directory_fd is not None:
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        except OSError as exc:
            raise CheckpointStoreError([
                S11Issue("A3_S11_CHECKPOINT_WRITE_FAILED", str(exc), details={"target": str(target)})
            ]) from exc
        finally:
            if temp_name is not None:
                Path(temp_name).unlink(missing_ok=True)
        return ArtifactRef(
            artifact_id=checkpoint_id,
            artifact_type="cycle_state_checkpoint",
            content_hash=actual_hash,
            schema_id="replay_state.v2",
            schema_version="2.0.0",
        )

    async def load(self, checkpoint_id: str) -> ReplayState:
        return await asyncio.to_thread(self._load_sync, checkpoint_id)

    def _load_sync(self, checkpoint_id: str) -> ReplayState:
        target = self._path(checkpoint_id)
        try:
            raw = target.read_bytes()
            data = json.loads(raw.decode("utf-8"))
            state = ReplayState.model_validate(data)
        except FileNotFoundError as exc:
            raise CheckpointStoreError([
                S11Issue("A3_S11_CHECKPOINT_NOT_FOUND", f"Checkpoint {checkpoint_id!r} not found")
            ]) from exc
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise CheckpointStoreError([
                S11Issue("A3_S11_CHECKPOINT_READ_FAILED", str(exc), details={"target": str(target)})
            ]) from exc
        return state
