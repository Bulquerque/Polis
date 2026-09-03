from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from ..runtime.cognition import continue_cognition
from ..runtime_shared.s21_models import (
    AttentionFollowupIntentPanel,
    CognitionConfig,
    InitialAgentReadingPanel,
    PreliminaryBeliefProposalPanel,
    ProviderAdapterRegistryConfig,
    SocialIntentPanel,
    ValidatedPersonContextBundle,
    ValidatedToolResultPanel,
)
from ..runtime_shared.s21_ports import S21Runtime
from ._s21_wrapper import parse_model, run_sync, serialize_outputs

MODULE_ID = "P3.S21.M05"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "llm_cognition_continuation_runner"
SUBPHASE = "P3.S21"
CONTRACT = "modules/P3_S21_M05_llm_cognition_continuation_runner.yaml"
REQUIRED_SERVICES = ("runtime",)
REQUIRED_INPUTS = ['initial_agent_reading_panel', 'preliminary_belief_proposal_panel', 'validated_tool_result_panel', 'validated_person_context_bundle', 'cognition_config', 'provider_adapter_registry_config', 'social_intent_panel', 'attention_followup_intent_panel']
PRODUCED_OUTPUTS = ('agent_reading_panel', 'raw_belief_proposal_panel', 'finalized_social_intent_panel', 'finalized_attention_followup_intent_panel')
IMPLEMENTED = True


@deprecated_legacy_entrypoint("P3.S21.M05")
async def run_module_async(
    inputs: Mapping[str, object], *, runtime: S21Runtime
) -> dict[str, object]:
    outputs = await continue_cognition(
        initial_readings=parse_model(
            inputs,
            "initial_agent_reading_panel",
            InitialAgentReadingPanel,
            module_id=MODULE_ID,
        ),
        preliminary_proposals=parse_model(
            inputs,
            "preliminary_belief_proposal_panel",
            PreliminaryBeliefProposalPanel,
            module_id=MODULE_ID,
        ),
        validated_tool_results=parse_model(
            inputs,
            "validated_tool_result_panel",
            ValidatedToolResultPanel,
            module_id=MODULE_ID,
        ),
        contexts=parse_model(
            inputs,
            "validated_person_context_bundle",
            ValidatedPersonContextBundle,
            module_id=MODULE_ID,
        ),
        cognition_config=parse_model(
            inputs, "cognition_config", CognitionConfig, module_id=MODULE_ID
        ),
        provider_registry=parse_model(
            inputs,
            "provider_adapter_registry_config",
            ProviderAdapterRegistryConfig,
            module_id=MODULE_ID,
        ),
        social_intents=parse_model(
            inputs, "social_intent_panel", SocialIntentPanel, module_id=MODULE_ID
        ),
        attention_intents=parse_model(
            inputs,
            "attention_followup_intent_panel",
            AttentionFollowupIntentPanel,
            module_id=MODULE_ID,
        ),
        runtime=runtime,
    )
    return serialize_outputs(outputs)


@deprecated_legacy_entrypoint("P3.S21.M05")
def run_module(
    inputs: Mapping[str, object],
    config: Mapping[str, object] | None = None,
    *,
    runtime: S21Runtime,
) -> dict[str, object]:
    del config
    return run_sync(run_module_async(inputs, runtime=runtime), module_id=MODULE_ID)

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Continue cognition through the canonical context-injected runtime."""
    runtime = context.services.get("runtime")
    if runtime is None:
        raise TypeError("ModuleExecutionContext.services['runtime'] is required")
    return dict(await run_module_async(inputs, runtime=runtime))



# Canonical Phase 3 module metadata.
IMPLEMENTATION_STATUS = 'IMPLEMENTED_QUALIFIED_INTERNAL'
