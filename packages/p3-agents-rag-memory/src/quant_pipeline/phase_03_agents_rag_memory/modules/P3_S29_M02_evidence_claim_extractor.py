from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping
from typing import Any

from ..s29_products import extract_evidence_claims

MODULE_ID = "P3.S29.M02"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "evidence_claim_extractor"
SUBPHASE = "P3.S29"
CONTRACT = "modules/P3_S29_M02_evidence_claim_extractor.yaml"
REQUIRED_INPUTS = [
    "evidence_bound_belief_update_panel",
    "retrieval_evidence_map",
    "graph_evidence_map",
    "rag_index_artifact",
    "agent_reading_panel",
]
PRODUCED_OUTPUTS = ('evidence_tag_panel',)
IMPLEMENTED = True


@deprecated_legacy_entrypoint("P3.S29.M02")
def run_module(
    inputs: Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project the structured claim-to-evidence chain without inventing tags."""

    if config is None:
        raise ValueError("P3.S29.M02 requires an explicit deterministic execution context")
    return extract_evidence_claims(inputs, config)

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
IMPLEMENTATION_STATUS = 'IMPLEMENTED_QUALIFIED_INTERNAL'
