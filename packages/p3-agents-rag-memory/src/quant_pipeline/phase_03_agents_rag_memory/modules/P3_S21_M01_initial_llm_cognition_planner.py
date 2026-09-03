from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from ..runtime.cognition import plan_initial_cognition
from ..runtime_shared.s21_models import (
    CognitionConfig,
    ProviderAdapterRegistryConfig,
    ValidatedPersonContextBundle,
)
from ..runtime_shared.s21_ports import S21Runtime
from ._s21_wrapper import parse_model, run_sync, serialize_outputs

MODULE_ID = "P3.S21.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "initial_llm_cognition_planner"
SUBPHASE = "P3.S21"
CONTRACT = "modules/P3_S21_M01_initial_llm_cognition_planner.yaml"
REQUIRED_SERVICES = ("runtime",)
REQUIRED_INPUTS = ['validated_person_context_bundle', 'cognition_config', 'provider_adapter_registry_config']
PRODUCED_OUTPUTS = ('initial_agent_reading_panel', 'preliminary_belief_proposal_panel', 'social_intent_panel', 'tool_call_request_panel', 'attention_followup_intent_panel')
IMPLEMENTED = True


@deprecated_legacy_entrypoint("P3.S21.M01")
async def run_module_async(
    inputs: Mapping[str, object], *, runtime: S21Runtime
) -> dict[str, object]:
    outputs = await plan_initial_cognition(
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
        runtime=runtime,
    )
    return serialize_outputs(outputs)


@deprecated_legacy_entrypoint("P3.S21.M01")
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
    """Execute cognition through the canonical context-injected runtime."""
    runtime = context.services.get("runtime")
    if runtime is None:
        raise TypeError("ModuleExecutionContext.services['runtime'] is required")
    return dict(await run_module_async(inputs, runtime=runtime))



# Canonical Phase 3 module metadata.
IMPLEMENTATION_STATUS = 'IMPLEMENTED_QUALIFIED_INTERNAL'
