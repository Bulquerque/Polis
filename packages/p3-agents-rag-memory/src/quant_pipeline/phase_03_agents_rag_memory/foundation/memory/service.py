from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .errors import MemoryIndexStoreError, S14Issue
from .hashing import canonical_json_bytes, canonicalize, hash_value, stable_id
from .index_planner import MemoryIndexPlanner
from .models import IndexPartitionRequest, IndexPartitionResult, MemoryAccessPolicy, MemoryIndexManifest
from .policy_compiler import MemoryPolicyCompiler
from .ports import MemoryIndexPort


def _log(logger: Callable[[str, dict[str, object]], None] | None, event: str, **fields: object) -> None:
    if logger is not None:
        logger(event, fields)


class LocalAtomicJsonlMemoryIndex:
    """Content-addressed local adapter used for offline qualification and replay."""

    adapter_id = "local_atomic_jsonl"
    adapter_version = "1.0.0"

    def __init__(self, root: Path) -> None:
        self.root = root

    def build_partition(self, request: IndexPartitionRequest) -> IndexPartitionResult:
        payload = b"".join(canonical_json_bytes(row) + b"\n" for row in request.entries)
        storage_hash = hashlib.sha256(payload).hexdigest()
        directory = self.root / request.partition_hash[:2]
        path = directory / f"{request.partition_hash}.jsonl"
        try:
            directory.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                temp = directory / f".{path.name}.tmp-{os.getpid()}"
                with temp.open("wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp, path)
            elif hashlib.sha256(path.read_bytes()).hexdigest() != storage_hash:
                raise MemoryIndexStoreError([
                    S14Issue(
                        code="P3_S14_INDEX_CONTENT_ADDRESS_COLLISION",
                        message="Existing index partition does not match its content-addressed path.",
                        path=str(path),
                    )
                ])
        except MemoryIndexStoreError:
            raise
        except OSError as exc:
            raise MemoryIndexStoreError([
                S14Issue(
                    code="P3_S14_INDEX_STORE_WRITE_FAILED",
                    message="Could not atomically persist the memory-index partition.",
                    path=str(path),
                    details={"error": str(exc)},
                )
            ]) from exc
        return IndexPartitionResult(
            partition_key=request.partition_key,
            index_ref=f"memory-index://local/{request.partition_hash}",
            record_count=len(request.entries),
            partition_hash=request.partition_hash,
            storage_hash=storage_hash,
        )


@dataclass(frozen=True, slots=True)
class MemoryPolicyBuilder:
    logger: Callable[[str, dict[str, object]], None] | None = None

    def run(self, **inputs: object) -> MemoryAccessPolicy:
        return MemoryPolicyCompiler(logger=self.logger).compile(**inputs)


@dataclass(frozen=True, slots=True)
class MemoryIndexManifestBuilder:
    index_port: MemoryIndexPort
    logger: Callable[[str, dict[str, object]], None] | None = None

    def run(self, **inputs: object) -> MemoryIndexManifest:
        return MemoryIndexPlanner(index_port=self.index_port, logger=self.logger).build(**inputs)


__all__ = [
    "LocalAtomicJsonlMemoryIndex",
    "MemoryIndexManifestBuilder",
    "MemoryPolicyBuilder",
    "canonical_json_bytes",
    "canonicalize",
    "hash_value",
    "stable_id",
]
