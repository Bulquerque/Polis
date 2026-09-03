from __future__ import annotations

from dataclasses import dataclass
import json

from pydantic import ValidationError

from .errors import BoundaryValidationError
from .contracts_internal import (
    FoundationGovernanceView,
    FoundationRuntimeManifest,
    KnowledgeRuntimeView,
    MemoryRuntimeView,
    PopulationRuntimeView,
    RuntimeFoundationContext,
    StateRuntimeView,
    ToolRuntimeView,
    content_hash,
)
from .ports import ArtifactResolverPort


@dataclass(frozen=True, slots=True)
class FoundationManifestConsumer:
    """Resolve a reference-based foundation manifest into a typed runtime context.

    The consumer validates manifest hash, pointer payload hashes, identity and cutoff.
    Storage and provider details remain behind ``ArtifactResolverPort``.
    """

    artifact_resolver: ArtifactResolverPort

    async def resolve(self, manifest: FoundationRuntimeManifest) -> RuntimeFoundationContext:
        if manifest.status.value in {"BLOCKED", "FAILED"}:
            raise BoundaryValidationError(
                f"foundation manifest is not consumable: status={manifest.status}"
            )
        manifest_payload = manifest.model_dump(mode="json", exclude={"content_hash"})
        if content_hash(manifest_payload) != manifest.content_hash:
            raise BoundaryValidationError("foundation manifest content_hash is invalid")
        governance = await self._resolve_view(manifest.governance_view, FoundationGovernanceView)
        population = await self._resolve_view(manifest.population_view, PopulationRuntimeView)
        state = await self._resolve_view(manifest.state_view, StateRuntimeView)
        knowledge = await self._resolve_view(manifest.knowledge_view, KnowledgeRuntimeView)
        memory = await self._resolve_view(manifest.memory_view, MemoryRuntimeView)
        tools = await self._resolve_view(manifest.tool_view, ToolRuntimeView)

        for label, view in (
            ("governance", governance),
            ("population", population),
            ("state", state),
            ("knowledge", knowledge),
            ("memory", memory),
            ("tools", tools),
        ):
            if view.run_id != manifest.run_id or view.snapshot_id != manifest.snapshot_id:
                raise BoundaryValidationError(f"{label} view identity does not match manifest")
            if view.as_of_time != manifest.as_of_time:
                raise BoundaryValidationError(f"{label} view cutoff does not match manifest")

        return RuntimeFoundationContext(
            manifest=manifest,
            governance=governance,
            population=population,
            state=state,
            knowledge=knowledge,
            memory=memory,
            tools=tools,
        )

    async def _resolve_view(self, pointer, model):
        if pointer.status.value in {"BLOCKED", "FAILED"}:
            raise BoundaryValidationError(
                f"foundation view pointer is not consumable: {pointer.artifact_name}={pointer.status}"
            )
        raw = await self.artifact_resolver.resolve(pointer)
        if raw.pointer != pointer:
            raise BoundaryValidationError(f"resolver returned a different pointer for {pointer.artifact_id}")
        try:
            view = model.model_validate_json(json.dumps(raw.payload))
        except ValidationError as exc:
            raise BoundaryValidationError(
                f"invalid foundation view payload for {pointer.artifact_name}: {exc}"
            ) from exc
        if pointer.schema_id != view.schema_id or pointer.schema_version != view.schema_version:
            raise BoundaryValidationError(
                f"pointer schema does not match resolved view: {pointer.artifact_name}"
            )
        if view.status.value in {"BLOCKED", "FAILED"}:
            raise BoundaryValidationError(
                f"resolved foundation view is not consumable: {pointer.artifact_name}={view.status}"
            )
        return view
