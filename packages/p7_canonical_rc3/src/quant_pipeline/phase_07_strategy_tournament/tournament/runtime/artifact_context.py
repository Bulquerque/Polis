from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..domain.errors import IntegrityViolation
from ..domain.reasoning import reason_prefix


@dataclass(slots=True)
class ArtifactContext:
    artifacts: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_inputs(cls, inputs: Mapping[str, Any]) -> "ArtifactContext":
        return cls(artifacts=dict(inputs))

    def select(self, names: tuple[str, ...], optional: tuple[str, ...] = ()) -> dict[str, Any]:
        selected = {name: self.artifacts[name] for name in names}
        selected.update({name: self.artifacts[name] for name in optional if name in self.artifacts})
        return selected

    def publish(self, outputs: Mapping[str, Any], *, module_id: str) -> None:
        for name, artifact in outputs.items():
            if name in self.artifacts and self.artifacts[name] != artifact:
                raise IntegrityViolation(
                    f"{reason_prefix(module_id)}_ARTIFACT_OVERWRITE_FORBIDDEN",
                    "module attempted to overwrite an existing artifact",
                    module_id=module_id,
                    details={"artifact_name": name},
                )
            self.artifacts[name] = artifact
