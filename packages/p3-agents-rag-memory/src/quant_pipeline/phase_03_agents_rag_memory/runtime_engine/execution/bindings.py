from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Mapping

from pydantic import JsonValue

from ..contracts_internal import (
    ArtifactPointer,
    CycleKernelRequest,
    RuntimeFoundationContext,
    RuntimeIssue,
)
from .catalog import MODULE_IMPORT_PATHS
from ..registry import RUNTIME_MODULE_IDS
from .models import ModuleInvocation
from .ports import JsonArtifactRepositoryPort, RuntimeConfigPort


@dataclass(frozen=True, slots=True)
class RuntimeDependencyRegistry:
    """Internal runtime objects for modules that explicitly require injected ports."""

    by_module_id: Mapping[str, object] = field(default_factory=dict)

    def get(self, module_id: str) -> object | None:
        return self.by_module_id.get(module_id)


class ConventionModuleBindings:
    """Resolve exact-name artifacts and configs without inventing defaults.

    Cross-domain shape conversion belongs in the integration layer before artifacts
    reach this provider. Missing inputs are reported, never converted to empty data.
    """

    def __init__(
        self,
        *,
        repository: JsonArtifactRepositoryPort,
        config: RuntimeConfigPort,
        runtime_dependencies: RuntimeDependencyRegistry | None = None,
    ) -> None:
        self._repository = repository
        self._config = config
        self._runtime_dependencies = runtime_dependencies or RuntimeDependencyRegistry()

    async def validate(
        self,
        module_ids: tuple[str, ...],
        request: CycleKernelRequest,
        foundation: RuntimeFoundationContext,
        artifacts: Mapping[str, ArtifactPointer],
    ) -> tuple[RuntimeIssue, ...]:
        pointers = self._pointer_index(foundation, artifacts, request=request)
        available_names = set(pointers)
        first_index = min(RUNTIME_MODULE_IDS.index(module_id) for module_id in module_ids)
        for earlier_id in RUNTIME_MODULE_IDS[:first_index]:
            earlier = importlib.import_module(MODULE_IMPORT_PATHS[earlier_id])
            available_names.update(str(item) for item in getattr(earlier, "PRODUCED_OUTPUTS", ()))
        issues: list[RuntimeIssue] = []
        for module_id in module_ids:
            module = importlib.import_module(MODULE_IMPORT_PATHS[module_id])
            required = tuple(str(item) for item in getattr(module, "REQUIRED_INPUTS", ()))
            for name in required:
                if name in available_names:
                    continue
                if await self._config.get(name) is not None:
                    continue
                issues.append(
                    RuntimeIssue(
                        code="MODULE_INPUT_NOT_BOUND",
                        message=f"{module_id} has no binding for required input {name}",
                        severity="ERROR",
                        module_id=module_id,
                    )
                )
            if tuple(getattr(module, "REQUIRED_SERVICES", ())) and self._runtime_dependencies.get(module_id) is None:
                issues.append(
                    RuntimeIssue(
                        code="MODULE_RUNTIME_NOT_BOUND",
                        message=f"{module_id} requires an injected runtime dependency",
                        severity="ERROR",
                        module_id=module_id,
                    )
                )
            # Dry-run validation follows the same topological contract as execution:
            # outputs declared by an earlier module are available to later modules.
            available_names.update(str(item) for item in getattr(module, "PRODUCED_OUTPUTS", ()))
        return tuple(issues)

    async def build(
        self,
        module_id: str,
        request: CycleKernelRequest,
        foundation: RuntimeFoundationContext,
        artifacts: Mapping[str, ArtifactPointer],
    ) -> ModuleInvocation:
        module = importlib.import_module(MODULE_IMPORT_PATHS[module_id])
        pointers = self._pointer_index(foundation, artifacts, request=request)
        inputs: dict[str, JsonValue] = {}
        for name in tuple(str(item) for item in getattr(module, "REQUIRED_INPUTS", ())):
            pointer = pointers.get(name)
            if pointer is not None:
                inputs[name] = await self._repository.read_json(pointer)
                continue
            value = await self._config.get(name)
            if value is None:
                raise KeyError(f"{module_id} required input is not bound: {name}")
            inputs[name] = value
        module_config = await self._config.get(f"module:{module_id}") or {}
        return ModuleInvocation(
            inputs=inputs,
            config=module_config,
            runtime=self._runtime_dependencies.get(module_id),
        )

    @staticmethod
    def _pointer_index(
        foundation: RuntimeFoundationContext,
        artifacts: Mapping[str, ArtifactPointer],
        *,
        request: CycleKernelRequest | None = None,
    ) -> dict[str, ArtifactPointer]:
        result = dict(artifacts)
        views = (
            foundation.governance,
            foundation.population,
            foundation.state,
            foundation.knowledge,
            foundation.memory,
            foundation.tools,
        )
        for view in views:
            for value in view.__dict__.values():
                if isinstance(value, ArtifactPointer):
                    result.setdefault(value.artifact_name, value)
        if foundation.manifest.prompt_bundle.artifact_name not in result:
            result[foundation.manifest.prompt_bundle.artifact_name] = foundation.manifest.prompt_bundle
        if foundation.manifest.model_registry.artifact_name not in result:
            result[foundation.manifest.model_registry.artifact_name] = foundation.manifest.model_registry
        aliases = {
            "current_person_state_panel": "current_person_state",
            "current_belief_state_panel": "current_belief_state",
            "prior_cycle_endogenous_stimulus_queue": "pending_stimuli",
            "belief_outcome_commitment_log": "belief_commitments",
        }
        if request is not None:
            result.setdefault(request.stimulus_ref.artifact_name, request.stimulus_ref)
            if request.schedule_context_ref is not None:
                result.setdefault(request.schedule_context_ref.artifact_name, request.schedule_context_ref)
            if request.prior_state is not None:
                replay_aliases = {
                    "current_person_state_panel": request.prior_state.person_state,
                    "current_belief_state_panel": request.prior_state.belief_state,
                    "current_memory_state": request.prior_state.memory_state,
                    "current_social_graph": request.prior_state.social_graph,
                    "prior_cycle_endogenous_stimulus_queue": request.prior_state.pending_stimuli,
                    "belief_outcome_commitment_log": request.prior_state.belief_commitments,
                }
                result.update(replay_aliases)
        for alias, source_name in aliases.items():
            if alias not in result and source_name in result:
                result[alias] = result[source_name]
        return result


@dataclass(slots=True)
class MappingRuntimeConfig:
    values: Mapping[str, dict[str, JsonValue]]

    async def get(self, key: str) -> dict[str, JsonValue] | None:
        value = self.values.get(key)
        return dict(value) if value is not None else None
