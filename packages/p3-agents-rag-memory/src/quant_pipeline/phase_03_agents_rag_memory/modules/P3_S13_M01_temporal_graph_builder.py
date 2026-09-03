from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from ..foundation.resources.temporal_graphrag.adapters import (
    DisabledGraphProposalProvider,
    InMemoryArtifactStore,
    ListEventSink,
    NvidiaNimGraphProposalProvider,
    NullGraphPublisher,
)
from ..foundation.resources.temporal_graphrag.compatibility import (
    normalize_graph_config,
    normalize_pit_context,
    normalize_provider_registry,
    normalize_rag_index,
    normalize_run_snapshot,
)
from ..foundation.resources.temporal_graphrag.errors import (
    ContractError,
    ErrorCategory,
    error,
)
from ..foundation.resources.temporal_graphrag.module_m01 import TemporalGraphBuilder
from ..orchestration.execution_profiles import ExecutionProfile, resolve_execution_profile
from ._runtime import run_coroutine

MODULE_ID = "P3.S13.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "temporal_graph_builder"
SUBPHASE = "P3.S13"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
REQUIRED_INPUTS = (
    "rag_index_artifact",
    "pit_validated_context",
    "phase3_run_snapshot",
    "graph_config",
    "provider_adapter_registry_config",
)
PRODUCED_OUTPUTS = ('graph_rag_artifact',)


def _missing_inputs(inputs: dict[str, Any]) -> tuple[str, ...]:
    return tuple(name for name in REQUIRED_INPUTS if name not in inputs)


def _validate_runtime_profile(
    *,
    profile: ExecutionProfile,
    runtime: dict[str, Any],
    graph_config: Any,
) -> None:
    artifact_store = runtime.get("artifact_store")
    proposal_provider = runtime.get("graph_proposal_provider")
    graph_publisher = runtime.get("graph_publisher")

    if profile is ExecutionProfile.TEST:
        return

    if artifact_store is None or isinstance(artifact_store, InMemoryArtifactStore):
        raise ContractError(
            error(
                "P3_S13_M01_PERSISTENT_STORE_REQUIRED",
                ErrorCategory.PERSISTENCE,
                f"{profile.value} requires an explicitly injected persistent artifact store",
            )
        )

    if graph_config.provider_proposals.enabled:
        if proposal_provider is None or isinstance(
            proposal_provider,
            DisabledGraphProposalProvider,
        ):
            raise ContractError(
                error(
                    "P3_S13_M01_GRAPH_PROVIDER_REQUIRED",
                    ErrorCategory.PROVIDER,
                    f"{profile.value} requires an explicit graph proposal provider when proposals are enabled",
                )
            )
        if profile is ExecutionProfile.REPLAY and isinstance(
            proposal_provider,
            NvidiaNimGraphProposalProvider,
        ):
            raise ContractError(
                error(
                    "P3_S13_M01_LIVE_PROVIDER_FORBIDDEN_IN_REPLAY",
                    ErrorCategory.PROVIDER,
                    "REPLAY must use a frozen/local proposal provider, not a live NVIDIA NIM adapter",
                )
            )

    if graph_config.publication.enabled and (
        graph_publisher is None or isinstance(graph_publisher, NullGraphPublisher)
    ):
        raise ContractError(
            error(
                "P3_S13_M01_GRAPH_PUBLISHER_REQUIRED",
                ErrorCategory.PERSISTENCE,
                f"{profile.value} requires an explicit graph publisher when publication is enabled",
            )
        )


@deprecated_legacy_entrypoint("P3.S13.M01")
async def run_module_async(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a temporal evidence-bound graph from the canonical RAG index."""
    missing = _missing_inputs(inputs)
    if missing:
        raise ContractError(
            error(
                "P3_S13_M01_INPUT_INVALID",
                ErrorCategory.CONTRACT,
                "required inputs are missing",
                context={"missing_inputs": list(missing)},
            )
        )

    settings = config or {}
    profile = resolve_execution_profile(settings)
    runtime = dict(settings.get("runtime", {}))
    graph_config = normalize_graph_config(inputs["graph_config"])
    _validate_runtime_profile(
        profile=profile,
        runtime=runtime,
        graph_config=graph_config,
    )

    service = TemporalGraphBuilder(
        artifact_store=runtime.get("artifact_store") or InMemoryArtifactStore(),
        proposal_provider=(
            runtime.get("graph_proposal_provider")
            or DisabledGraphProposalProvider()
        ),
        graph_publisher=runtime.get("graph_publisher") or NullGraphPublisher(),
        event_sink=runtime.get("event_sink") or ListEventSink(),
    )
    artifact = await service.run(
        rag_index=normalize_rag_index(inputs["rag_index_artifact"]),
        context=normalize_pit_context(inputs["pit_validated_context"]),
        snapshot=normalize_run_snapshot(inputs["phase3_run_snapshot"]),
        graph_config=graph_config,
        provider_registry=normalize_provider_registry(
            inputs["provider_adapter_registry_config"]
        ),
    )
    return artifact.model_dump(mode="json")


@deprecated_legacy_entrypoint("P3.S13.M01")
def run_module(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return run_coroutine(run_module_async(inputs, config))

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
CONTRACT = 'modules/P3_S13_M01_temporal_graph_builder.yaml'
