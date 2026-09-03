from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from ..runtime.cognition import parse_structured_beliefs
from ..runtime_shared.s21_models import PropositionRegistryConfig, RawBeliefProposalPanel
from ._s21_wrapper import parse_model

MODULE_ID = "P3.S21.M06"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "structured_belief_proposal_parser"
SUBPHASE = "P3.S21"
CONTRACT = "modules/P3_S21_M06_structured_belief_proposal_parser.yaml"
REQUIRED_INPUTS = ['raw_belief_proposal_panel', 'proposition_registry_config']
PRODUCED_OUTPUTS = ('structured_belief_proposal_panel',)
IMPLEMENTED = True


@deprecated_legacy_entrypoint("P3.S21.M06")
def run_module(
    inputs: Mapping[str, object],
    config: Mapping[str, object] | None = None,
) -> dict[str, object]:
    del config
    output = parse_structured_beliefs(
        raw_proposals=parse_model(
            inputs,
            "raw_belief_proposal_panel",
            RawBeliefProposalPanel,
            module_id=MODULE_ID,
        ),
        proposition_registry=parse_model(
            inputs,
            "proposition_registry_config",
            PropositionRegistryConfig,
            module_id=MODULE_ID,
        ),
    )
    return {"structured_belief_proposal_panel": output.model_dump(mode="json")}

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
IMPLEMENTATION_STATUS = 'IMPLEMENTED_QUALIFIED_INTERNAL'
