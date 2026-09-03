from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .models import ArtifactRef, CycleKernelRequest, CycleKernelResult, ReplayState


class CycleKernelPort(Protocol):
    """Stable runtime boundary used by warm-up replay."""

    contract_version: str

    async def execute_cycle(self, request: CycleKernelRequest) -> CycleKernelResult:
        """Execute one canonical S17-S26 cycle in WARMUP_REPLAY mode."""
        ...


class CheckpointStorePort(Protocol):
    """Durable checkpoint storage without leaking storage technology into domain code."""

    async def write(self, checkpoint_id: str, state: ReplayState) -> ArtifactRef:
        ...

    async def load(self, checkpoint_id: str) -> ReplayState:
        ...


class CheckpointPathProvider(Protocol):
    def path_for(self, checkpoint_id: str) -> Path:
        ...
