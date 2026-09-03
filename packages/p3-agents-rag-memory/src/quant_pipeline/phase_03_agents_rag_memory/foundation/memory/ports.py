from __future__ import annotations

from typing import Protocol

from .models import IndexPartitionRequest, IndexPartitionResult


class MemoryIndexPort(Protocol):
    """Persist deterministic memory-index partitions behind a stable boundary."""

    def build_partition(self, request: IndexPartitionRequest) -> IndexPartitionResult:
        ...
