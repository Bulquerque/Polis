from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from ..foundation.resources.temporal_graphrag.adapters import (
    InMemoryArtifactStore,
    ListEventSink,
)
from ..foundation.resources.temporal_graphrag.compatibility import (
    normalize_graph_config,
    normalize_rag_index,
)
from ..foundation.resources.temporal_graphrag.errors import (
    ContractError,
    ErrorCategory,
    error,
)
from ..foundation.resources.temporal_graphrag.models import GraphRagArtifact
from ..foundation.resources.temporal_graphrag.module_m02 import GraphEvidenceLinker
from ..orchestration.execution_profiles import ExecutionProfile, resolve_execution_profile

MODULE_ID = "P3.S13.M02"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "graph_evidence_linker"
SUBPHASE = "P3.S13"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"
REQUIRED_INPUTS = (
    "graph_rag_artifact",
    "rag_index_artifact",
    "graph_config",
)
PRODUCED_OUTPUTS = ('graph_evidence_map',)


@deprecated_legacy_entrypoint("P3.S13.M02")
def run_module(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind graph claims and edges to immutable retrieval evidence."""
    missing = tuple(name for name in REQUIRED_INPUTS if name not in inputs)
    if missing:
        raise ContractError(
            error(
                "P3_S13_M02_INPUT_INVALID",
                ErrorCategory.CONTRACT,
                "required inputs are missing",
                context={"missing_inputs": list(missing)},
            )
        )

    settings = config or {}
    profile = resolve_execution_profile(settings)
    runtime = dict(settings.get("runtime", {}))
    artifact_store = runtime.get("artifact_store")
    if profile is not ExecutionProfile.TEST and (
        artifact_store is None or isinstance(artifact_store, InMemoryArtifactStore)
    ):
        raise ContractError(
            error(
                "P3_S13_M02_PERSISTENT_STORE_REQUIRED",
                ErrorCategory.PERSISTENCE,
                f"{profile.value} requires an explicitly injected persistent artifact store",
            )
        )

    service = GraphEvidenceLinker(
        artifact_store=artifact_store or InMemoryArtifactStore(),
        event_sink=runtime.get("event_sink") or ListEventSink(),
    )
    artifact = service.run(
        graph=GraphRagArtifact.model_validate(
            inputs["graph_rag_artifact"],
            strict=False,
        ),
        rag_index=normalize_rag_index(inputs["rag_index_artifact"]),
        graph_config=normalize_graph_config(inputs["graph_config"]),
    )
    return artifact.model_dump(mode="json")

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
CONTRACT = 'modules/P3_S13_M02_graph_evidence_linker.yaml'
