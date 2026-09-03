"""Deterministic fail-closed orchestration over canonical module requests."""
from __future__ import annotations

from dataclasses import dataclass

from .context import P5ExecutionContext
from .domain.core import ArtifactReference, ModuleRequest, ModuleResult, ModuleStatus
from .orchestration.executor import execute_module
from .registry import get_module


@dataclass(frozen=True, slots=True)
class PhaseRunResult:
    results: tuple[ModuleResult, ...]
    artifacts: dict[str, ArtifactReference]

    @property
    def status(self) -> ModuleStatus:
        if any(item.status in {ModuleStatus.FAILED, ModuleStatus.REJECTED} for item in self.results):
            return ModuleStatus.FAILED
        if any(item.status is ModuleStatus.DEGRADED for item in self.results):
            return ModuleStatus.DEGRADED
        return ModuleStatus.SUCCESS


class PhaseRunner:
    def __init__(self, context: P5ExecutionContext) -> None:
        self.context = context

    def run(
        self,
        requests: tuple[ModuleRequest, ...],
        *,
        initial_artifacts: dict[str, ArtifactReference] | None = None,
        fail_fast: bool = True,
    ) -> PhaseRunResult:
        artifacts = dict(initial_artifacts or {})
        results: list[ModuleResult] = []
        for request in requests:
            try:
                descriptor = get_module(request.module_id)
            except KeyError:
                descriptor = None
            resolved_inputs = {
                name: artifacts[name]
                for name in ((descriptor.required_inputs + descriptor.optional_inputs) if descriptor is not None else ())
                if name in artifacts
            }
            enriched = request.model_copy(update={
                "input_artifacts": {**resolved_inputs, **request.input_artifacts},
            })
            result = execute_module(enriched, self.context)
            results.append(result)
            for name, reference in result.outputs.items():
                if name in artifacts and artifacts[name].content_hash != reference.content_hash:
                    raise RuntimeError(f"artifact {name} would be overwritten by a different value")
                artifacts[name] = reference
            if fail_fast and result.status in {ModuleStatus.FAILED, ModuleStatus.REJECTED}:
                break
        return PhaseRunResult(results=tuple(results), artifacts=artifacts)
