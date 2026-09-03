from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from ..foundation.population.s5.generation import (
    PersonalityCandidateGenerator,
    PromptAsset,
)
from ..foundation.population.s5.models import GenerationRequest, ProviderKind
from ..orchestration.execution_profiles import ExecutionProfile, resolve_execution_profile

MODULE_ID = "P3.S5.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "personality_candidate_generator"
SUBPHASE = "P3.S5"
from ._input_builders import model_from_declared_inputs

IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"


@deprecated_legacy_entrypoint("P3.S5.M01")
async def run_module_async(
    inputs: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Generate a validated candidate batch through an injected provider."""
    prompt_data = config["prompt"]
    prompt = (
        prompt_data
        if isinstance(prompt_data, PromptAsset)
        else PromptAsset(**prompt_data)
    )
    request = model_from_declared_inputs(
        GenerationRequest,
        inputs,
        aliases={"retry_policy": "personality_creator_retry_policy_config"},
        injected={"run_context": config["run_context"]},
    )
    profile = resolve_execution_profile(config)
    selected_provider = request.provider_adapter_registry_config.selected_provider()
    if profile is ExecutionProfile.REPLAY:
        raise RuntimeError("P3.S5.M01 cannot generate new personalities during REPLAY")
    if profile is ExecutionProfile.LIVE and selected_provider.provider_kind is ProviderKind.FIXTURE:
        raise RuntimeError("P3.S5.M01 LIVE requires a non-fixture qualified provider")
    generator = PersonalityCandidateGenerator(
        provider=config["provider"],
        prompt=prompt,
        **({"sleep": config["sleep"]} if config.get("sleep") is not None else {}),
    )
    result = await generator.execute(request)
    return {
        "personality_candidate_pool": (
            result.personality_candidate_pool.model_dump(mode="json")
        ),
        "personality_creator_generation_audit": (
            result.personality_creator_generation_audit.model_dump(mode="json")
        ),
    }

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
CONTRACT = 'modules/P3_S5_M01_personality_candidate_generator.yaml'
REQUIRED_INPUTS = ('personality_tag_registry', 'person_schema_policy', 'population_generation_config', 'prior_population_generation_state', 'provider_adapter_registry_config', 'personality_creator_retry_policy_config')
PRODUCED_OUTPUTS = ('personality_candidate_pool', 'personality_creator_generation_audit')
