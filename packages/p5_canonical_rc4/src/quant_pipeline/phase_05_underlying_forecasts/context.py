"""Injected execution context shared by all P5 modules."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .domain.core import ExecutionMode, RunIdentity
from .events import EventRecorder
from .stores import JsonArtifactStore


@dataclass(slots=True)
class P5ExecutionContext:
    identity: RunIdentity
    mode: ExecutionMode
    artifact_root: Path
    recorder: EventRecorder = field(default_factory=EventRecorder)
    _artifact_store: JsonArtifactStore = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.artifact_root = Path(self.artifact_root).resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self._artifact_store = JsonArtifactStore(self.artifact_root)

    @property
    def artifact_store(self) -> JsonArtifactStore:
        return self._artifact_store

    @property
    def run_id(self) -> str:
        return self.identity.run_id

    @property
    def cycle_id(self) -> str:
        return self.identity.cycle_id

    @property
    def as_of_time(self):
        return self.identity.as_of_time

    @property
    def generated_at(self):
        return self.identity.generated_at

    @property
    def seed(self) -> int:
        return self.identity.seed
