"""Atomic checkpoint persistence helpers for P3.S26.M03."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path

from pydantic import ValidationError

from .artifacts import CycleStateSnapshotOut
from .common import canonical_json, content_hash
from .errors import S26PersistenceError


def write_checkpoint_atomic(snapshot: CycleStateSnapshotOut, destination: Path, *, exactly_once_ledger=None) -> Path:
    """Write an immutable checkpoint with hash validation and atomic replacement."""

    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = snapshot.model_dump(mode="json", exclude_none=True)
    expected_hash = content_hash({key: value for key, value in payload.items() if key != "content_hash"})
    if payload["content_hash"] != expected_hash:
        raise S26PersistenceError("invalid checkpoint hash")
    if exactly_once_ledger is not None:
        decision = exactly_once_ledger.admit(f"checkpoint:{snapshot.run_id}:{snapshot.target_cycle_id}", payload)
        if decision.decision.value == "DUPLICATE_CONFLICT":
            raise S26PersistenceError("checkpoint idempotency conflict")

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(canonical_json(payload) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, destination)
        _sync_dir(destination.parent)
        return destination
    except OSError as exc:
        if temporary_path is not None:
            with suppress(OSError):
                temporary_path.unlink()
        raise S26PersistenceError(f"checkpoint persistence failed: {exc}") from exc


def read_checkpoint(path: Path) -> CycleStateSnapshotOut:
    """Load and validate a checkpoint, including its canonical content hash."""

    try:
        raw_text = path.read_text(encoding="utf-8")
        payload = json.loads(raw_text)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise S26PersistenceError(f"checkpoint read failed: {exc}") from exc

    if not isinstance(payload, dict):
        raise S26PersistenceError("checkpoint payload must be a JSON object")

    try:
        result = CycleStateSnapshotOut.model_validate(payload)
    except ValidationError as exc:
        raise S26PersistenceError(f"checkpoint validation failed: {exc}") from exc

    expected_hash = content_hash({key: value for key, value in payload.items() if key != "content_hash"})
    if result.content_hash != expected_hash:
        raise S26PersistenceError("checkpoint hash mismatch")
    return result


def _sync_dir(path: Path) -> None:
    """Best-effort directory fsync after an atomic replace."""

    try:
        descriptor = os.open(path, getattr(os, "O_DIRECTORY", 0) | os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
