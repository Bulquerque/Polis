from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from ..s30_products import build_phase4_social_handoff

MODULE_ID = "P3.S30.M04"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "phase4_social_handoff_builder"
SUBPHASE = "P3.S30"
CONTRACT = "modules/P3_S30_M04_phase4_social_handoff_builder.yaml"
REQUIRED_INPUTS = (
    "social_feature_panel",
    "evidence_tag_panel",
    "agent_disagreement_panel",
    "context_memory_feature_panel",
    "hypothesis_registry",
    "phase3_run_snapshot",
)
PRODUCED_OUTPUTS = ('phase4_social_handoff_manifest',)
IMPLEMENTED = True


@deprecated_legacy_entrypoint("P3.S30.M04")
def run_module(inputs: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    context = config.get("execution_context")
    if not isinstance(context, dict):
        raise ValueError("P3.S30.M04 requires an explicit deterministic execution context")
    expected_hashes = config.get("expected_artifact_hashes")
    if expected_hashes is not None and not isinstance(expected_hashes, dict):
        raise ValueError("expected_artifact_hashes must be a mapping when provided")
    return build_phase4_social_handoff(inputs, context, expected_hashes)

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
IMPLEMENTATION_STATUS = 'IMPLEMENTED_QUALIFIED_INTERNAL'
