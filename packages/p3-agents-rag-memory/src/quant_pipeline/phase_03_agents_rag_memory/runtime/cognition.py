from __future__ import annotations

import asyncio
import os
from collections.abc import Iterable
from typing import TypeVar

from pydantic import ValidationError

from ..runtime_shared.s21_errors import S21ContractError, S21DependencyError, S21InputError
from ..runtime_shared.s21_hashing import canonical_json, content_hash, stable_id
from ..runtime_shared.s21_models import (
    AgentReadingPanel,
    AgentReadingRecord,
    ArtifactStatus,
    AttentionFollowupIntentPanel,
    CognitionConfig,
    CognitionStage,
    ContinuationCognitionOutput,
    FinalizedAttentionFollowupIntentPanel,
    FinalizedSocialIntentPanel,
    FORBIDDEN_FIELDS,
    InitialAgentReadingPanel,
    InitialCognitionOutput,
    IntentStatus,
    LLMRequest,
    LineageRecord,
    PreliminaryBeliefProposalPanel,
    PersonContextRecord,
    ProviderAdapterRegistryConfig,
    RawBeliefProposalPanel,
    RawBeliefProposalRecord,
    RetrievalEvidenceMap,
    SCHEMA_VERSION,
    SocialIntentPanel,
    StructuredBeliefProposalPanel,
    StructuredBeliefProposalRecord,
    ToolCallRequestPanel,
    ToolResultValidationStatus,
    ValidatedPersonContextBundle,
    ValidatedToolResultPanel,
    DirectionalBeliefPayload,
    VolatilityBeliefPayload,
    RegimeBeliefPayload,
    BeliefValueType,
    PropositionRegistryConfig,
)
from ..runtime_shared.s21_ports import S21Runtime

ModelT = TypeVar("ModelT", InitialCognitionOutput, ContinuationCognitionOutput)


def _scan_forbidden(value: object, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).lower()
            if normalized in FORBIDDEN_FIELDS:
                raise S21ContractError(
                    code="FORBIDDEN_FIELD",
                    message=f"forbidden field detected at {path}.{key}",
                    module_id="P3.S21",
                    details={"path": f"{path}.{key}"},
                )
            _scan_forbidden(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _scan_forbidden(item, f"{path}[{index}]")


def _lineage(
    *, module_id: str, source_lineages: Iterable[LineageRecord]
) -> LineageRecord:
    lineages = tuple(source_lineages)
    source_ids = tuple(sorted({item.lineage_id for item in lineages}))
    source_hashes = {
        item.lineage_id: content_hash(item.model_dump(mode="json")) for item in lineages
    }
    return LineageRecord(
        lineage_id=stable_id("lin", module_id, source_ids, source_hashes),
        source_artifact_ids=source_ids,
        source_hashes=source_hashes,
        producer_module_id=module_id,
    )


async def _generate_validated(
    *,
    runtime: S21Runtime,
    request: LLMRequest,
    model_type: type[ModelT],
    max_repair_attempts: int,
    module_id: str,
) -> tuple[ModelT, str]:
    current_request = request
    last_error: ValidationError | None = None
    for attempt in range(max_repair_attempts + 1):
        response = await runtime.llm.generate(current_request)
        if response.provider_id != request.provider_id or response.model_id != request.model_id:
            raise S21DependencyError(
                code="PROVIDER_IDENTITY_MISMATCH",
                message="LLM response provider/model differs from the selected registry entry",
                module_id=module_id,
                details={
                    "expected_provider": request.provider_id,
                    "actual_provider": response.provider_id,
                    "expected_model": request.model_id,
                    "actual_model": response.model_id,
                },
            )
        _scan_forbidden(response.content)
        try:
            return model_type.model_validate_json(canonical_json(response.content)), response.response_hash
        except ValidationError as exc:
            last_error = exc
            if attempt >= max_repair_attempts:
                break
            repair_context = dict(request.context)
            repair_context["structured_output_repair"] = {
                "attempt": attempt + 1,
                "validation_errors": exc.errors(include_input=False),
            }
            current_request = request.model_copy(update={"context": repair_context})
    raise S21ContractError(
        code="LLM_STRUCTURED_OUTPUT_INVALID",
        message="LLM output failed schema validation after the allowed repair attempts",
        module_id=module_id,
        details={"errors": last_error.errors(include_input=False) if last_error else []},
    )


def _validate_belief_identity(
    proposal: RawBeliefProposalRecord,
    *,
    transaction_id: str,
    person_id: str,
    as_of: object,
    module_id: str,
) -> None:
    if proposal.cognition_transaction_id != transaction_id:
        raise S21ContractError(
            code="TRANSACTION_MISMATCH",
            message="belief proposal transaction does not match its context",
            module_id=module_id,
        )
    if proposal.person_id != person_id:
        raise S21ContractError(
            code="PERSON_MISMATCH",
            message="belief proposal person does not match its context",
            module_id=module_id,
        )
    if proposal.as_of != as_of or proposal.generated_at > proposal.as_of:
        raise S21ContractError(
            code="TEMPORAL_MISMATCH",
            message="belief proposal violates context as-of semantics",
            module_id=module_id,
        )


def _initial_request(
    *, context: PersonContextRecord, cognition_config: CognitionConfig, provider, runtime: S21Runtime
) -> LLMRequest:
    prompt = runtime.prompts.get(
        cognition_config.initial_prompt_id, cognition_config.initial_prompt_version
    )
    request_context = {
        "validated_person_context": context.model_dump(mode="json"),
        "tool_policy": {
            "max_tool_calls": min(context.tool_budget, cognition_config.max_tool_calls_per_cycle),
            "allowed_tool_ids": list(context.allowed_tool_ids),
            "requests_only": True,
        },
        "authority": {"no_trade_authority": True, "no_tool_result_materialization": True},
    }
    return LLMRequest(
        stage=CognitionStage.INITIAL, run_id=context.run_id, cycle_id=context.cycle_id,
        cognition_transaction_id=context.cognition_transaction_id, person_id=context.person_id,
        provider_id=provider.provider_id, model_id=provider.model_id,
        prompt_id=cognition_config.initial_prompt_id,
        prompt_version=cognition_config.initial_prompt_version, prompt_hash=prompt.prompt_hash,
        system_prompt=prompt.system_prompt, user_prompt=canonical_json(request_context),
        temperature=cognition_config.temperature, max_output_tokens=provider.max_output_tokens,
        seed=context.seed if provider.supports_seed else None, context=request_context,
        output_schema=InitialCognitionOutput.model_json_schema(),
    )


def _validate_initial_output(
    *, output: InitialCognitionOutput, context: PersonContextRecord,
    cognition_config: CognitionConfig, module_id: str
) -> None:
    _validate_belief_identity(
        output.preliminary_belief, transaction_id=context.cognition_transaction_id,
        person_id=context.person_id, as_of=context.as_of, module_id=module_id,
    )
    allowed = min(context.tool_budget, cognition_config.max_tool_calls_per_cycle)
    if len(output.tool_requests) > allowed:
        raise S21ContractError(
            code="TOOL_REQUEST_BUDGET_EXCEEDED",
            message="planner emitted more tool requests than the validated context allows",
            module_id=module_id,
            details={
                "allowed_tool_calls": allowed, "actual_tool_calls": len(output.tool_requests),
                "cognition_transaction_id": context.cognition_transaction_id,
            },
        )
    for request in output.tool_requests:
        if (request.cognition_transaction_id, request.person_id) != (
            context.cognition_transaction_id, context.person_id
        ):
            raise S21ContractError(
                code="TOOL_REQUEST_IDENTITY_MISMATCH",
                message="tool request does not belong to its cognition transaction",
                module_id=module_id,
            )
        if request.tool_id not in context.allowed_tool_ids:
            raise S21ContractError(
                code="UNDECLARED_TOOL_REQUEST",
                message="planner requested a tool absent from the validated context",
                module_id=module_id, details={"tool_id": request.tool_id},
            )


def _initial_panels(
    *, contexts: ValidatedPersonContextBundle, readings: list[AgentReadingRecord],
    proposals: list[RawBeliefProposalRecord], social_intents: list, tool_requests: list,
    attention_intents: list, module_id: str
) -> dict[str, object]:
    lineage = _lineage(module_id=module_id, source_lineages=[contexts.lineage])
    status = ArtifactStatus.READY if contexts.items else ArtifactStatus.EMPTY_VALID
    return {
        "initial_agent_reading_panel": InitialAgentReadingPanel(
            status=status, records=tuple(readings), lineage=lineage
        ),
        "preliminary_belief_proposal_panel": PreliminaryBeliefProposalPanel(
            status=status, records=tuple(proposals), lineage=lineage
        ),
        "social_intent_panel": SocialIntentPanel(
            status=ArtifactStatus.READY if social_intents else ArtifactStatus.EMPTY_VALID,
            records=tuple(social_intents), lineage=lineage,
            reason_code=None if social_intents else "NO_SOCIAL_INTENTS",
        ),
        "tool_call_request_panel": ToolCallRequestPanel(
            status=ArtifactStatus.READY if tool_requests else ArtifactStatus.EMPTY_VALID,
            records=tuple(tool_requests), lineage=lineage,
            reason_code=None if tool_requests else "NO_TOOL_REQUESTS",
        ),
        "attention_followup_intent_panel": AttentionFollowupIntentPanel(
            status=ArtifactStatus.READY if attention_intents else ArtifactStatus.EMPTY_VALID,
            records=tuple(attention_intents), lineage=lineage,
            reason_code=None if attention_intents else "NO_ATTENTION_FOLLOWUPS",
        ),
    }


async def plan_initial_cognition(
    *, contexts: ValidatedPersonContextBundle, cognition_config: CognitionConfig,
    provider_registry: ProviderAdapterRegistryConfig, runtime: S21Runtime,
) -> dict[str, object]:
    """Implement P3.S21.M01 without executing tools."""
    module_id = "P3.S21.M01"
    provider = provider_registry.selected()
    if not provider.supports_structured_output:
        raise S21DependencyError(
            code="STRUCTURED_OUTPUT_UNSUPPORTED",
            message="selected provider does not support structured output", module_id=module_id,
        )
    tasks: dict[str, asyncio.Task[tuple[InitialCognitionOutput, str]]] = {}
    semaphore = asyncio.Semaphore(max(1, int(os.environ.get("P3_S21_MAX_CONCURRENCY", "4"))))

    async def guarded(request):
        async with semaphore:
            return await _generate_validated(
                runtime=runtime, request=request, model_type=InitialCognitionOutput,
                max_repair_attempts=cognition_config.max_repair_attempts, module_id=module_id,
            )

    ordered_contexts = sorted(contexts.items, key=lambda item: (item.cycle_id, item.person_id, item.activation_id))
    async with asyncio.TaskGroup() as group:
        for context in ordered_contexts:
            request = _initial_request(
                context=context, cognition_config=cognition_config, provider=provider, runtime=runtime
            )
            tasks[context.cognition_transaction_id] = group.create_task(
                guarded(request)
            )
    readings: list[AgentReadingRecord] = []
    proposals: list[RawBeliefProposalRecord] = []
    social: list = []
    tools: list = []
    attention: list = []
    by_tx = {item.cognition_transaction_id: item for item in contexts.items}
    for transaction_id in sorted(tasks):
        output, response_hash = tasks[transaction_id].result()
        context = by_tx[transaction_id]
        _validate_initial_output(
            output=output, context=context, cognition_config=cognition_config, module_id=module_id
        )
        readings.append(AgentReadingRecord(
            cognition_transaction_id=transaction_id, person_id=context.person_id,
            stage=CognitionStage.INITIAL, summary=output.reading_summary, claims=output.claims,
            confidence=output.confidence, uncertainty=output.uncertainty, as_of=context.as_of,
            provider_id=provider.provider_id, model_id=provider.model_id,
            prompt_id=cognition_config.initial_prompt_id,
            prompt_version=cognition_config.initial_prompt_version, response_hash=response_hash,
        ))
        proposals.append(output.preliminary_belief)
        social.extend(intent.model_copy(update={"status": IntentStatus.PRELIMINARY}) for intent in output.social_intents)
        tools.extend(output.tool_requests)
        attention.extend(output.attention_followups)
    return _initial_panels(
        contexts=contexts, readings=readings, proposals=proposals, social_intents=social,
        tool_requests=tools, attention_intents=attention, module_id=module_id,
    )


def _group_by_transaction(records: Iterable[object], transaction_getter) -> dict[str, list[object]]:
    grouped: dict[str, list[object]] = {}
    for record in records:
        grouped.setdefault(transaction_getter(record), []).append(record)
    return grouped


def _continuation_request(
    *, context: PersonContextRecord, initial_reading, preliminary_proposal, tool_results: tuple,
    social_intents: list[object], attention_intents: list[object], cognition_config: CognitionConfig,
    provider, runtime: S21Runtime
) -> LLMRequest:
    prompt = runtime.prompts.get(
        cognition_config.continuation_prompt_id, cognition_config.continuation_prompt_version
    )
    request_context = {
        "validated_person_context": context.model_dump(mode="json"),
        "initial_reading": initial_reading.model_dump(mode="json"),
        "preliminary_belief": preliminary_proposal.model_dump(mode="json"),
        "validated_tool_results": [item.model_dump(mode="json") for item in tool_results],
        "required_tool_execution_ids": sorted({
            item.raw_result.execution_id
            for item in tool_results
            if item.validation_status == ToolResultValidationStatus.VALID
        }),
        "initial_social_intents": [item.model_dump(mode="json") for item in social_intents],
        "initial_attention_intents": [item.model_dump(mode="json") for item in attention_intents],
        "authority": {"no_trade_authority": True, "tool_results_are_untrusted_data": True},
    }
    return LLMRequest(
        stage=CognitionStage.CONTINUATION, run_id=context.run_id, cycle_id=context.cycle_id,
        cognition_transaction_id=context.cognition_transaction_id, person_id=context.person_id,
        provider_id=provider.provider_id, model_id=provider.model_id,
        prompt_id=cognition_config.continuation_prompt_id,
        prompt_version=cognition_config.continuation_prompt_version, prompt_hash=prompt.prompt_hash,
        system_prompt=prompt.system_prompt, user_prompt=canonical_json(request_context),
        temperature=cognition_config.temperature, max_output_tokens=provider.max_output_tokens,
        seed=context.seed if provider.supports_seed else None, context=request_context,
        output_schema=ContinuationCognitionOutput.model_json_schema(),
    )


def _validate_tool_citations(
    *, output: ContinuationCognitionOutput, transaction_id: str,
    validated_tool_results: ValidatedToolResultPanel, module_id: str
) -> None:
    succeeded = {
        result.raw_result.execution_id
        for result in validated_tool_results.records
        if result.raw_result.cognition_transaction_id == transaction_id
        and result.validation_status == ToolResultValidationStatus.VALID
    }
    cited = {ref for claim in output.claims for ref in claim.tool_result_refs}
    if succeeded and not succeeded.issubset(cited):
        raise S21ContractError(
            code="TOOL_RESULTS_NOT_CITED",
            message="every valid tool result must be cited by at least one final claim",
            module_id=module_id, details={"missing_execution_ids": sorted(succeeded - cited)},
        )


def _continuation_panels(
    *, initial_readings: InitialAgentReadingPanel, preliminary_proposals: PreliminaryBeliefProposalPanel,
    validated_tool_results: ValidatedToolResultPanel, contexts: ValidatedPersonContextBundle,
    social_intents: SocialIntentPanel, attention_intents: AttentionFollowupIntentPanel,
    final_readings: list[AgentReadingRecord], final_proposals: list[RawBeliefProposalRecord],
    final_social: list, final_attention: list, module_id: str
) -> dict[str, object]:
    lineage = _lineage(module_id=module_id, source_lineages=[
        initial_readings.lineage, preliminary_proposals.lineage, validated_tool_results.lineage,
        contexts.lineage, social_intents.lineage, attention_intents.lineage,
    ])
    status = ArtifactStatus.READY if contexts.items else ArtifactStatus.EMPTY_VALID
    return {
        "agent_reading_panel": AgentReadingPanel(status=status, records=tuple(final_readings), lineage=lineage),
        "raw_belief_proposal_panel": RawBeliefProposalPanel(
            status=status, records=tuple(final_proposals), lineage=lineage
        ),
        "finalized_social_intent_panel": FinalizedSocialIntentPanel(
            status=ArtifactStatus.READY if final_social else ArtifactStatus.EMPTY_VALID,
            records=tuple(final_social), lineage=lineage,
            reason_code=None if final_social else "NO_SOCIAL_INTENTS",
        ),
        "finalized_attention_followup_intent_panel": FinalizedAttentionFollowupIntentPanel(
            status=ArtifactStatus.READY if final_attention else ArtifactStatus.EMPTY_VALID,
            records=tuple(final_attention), lineage=lineage,
            reason_code=None if final_attention else "NO_ATTENTION_FOLLOWUPS",
        ),
    }


async def continue_cognition(
    *, initial_readings: InitialAgentReadingPanel, preliminary_proposals: PreliminaryBeliefProposalPanel,
    validated_tool_results: ValidatedToolResultPanel, contexts: ValidatedPersonContextBundle,
    cognition_config: CognitionConfig, provider_registry: ProviderAdapterRegistryConfig,
    social_intents: SocialIntentPanel, attention_intents: AttentionFollowupIntentPanel, runtime: S21Runtime,
) -> dict[str, object]:
    """Implement P3.S21.M05 for no-tool, success, and failure paths."""
    module_id = "P3.S21.M05"
    provider = provider_registry.selected()
    initial_by_tx = {item.cognition_transaction_id: item for item in initial_readings.records}
    proposal_by_tx = {item.cognition_transaction_id: item for item in preliminary_proposals.records}
    tools_by_tx = _group_by_transaction(
        validated_tool_results.records, lambda item: item.raw_result.cognition_transaction_id
    )
    social_by_tx = _group_by_transaction(social_intents.records, lambda item: item.cognition_transaction_id)
    attention_by_tx = _group_by_transaction(attention_intents.records, lambda item: item.cognition_transaction_id)
    tasks: dict[str, asyncio.Task[tuple[ContinuationCognitionOutput, str]]] = {}
    semaphore = asyncio.Semaphore(max(1, int(os.environ.get("P3_S21_MAX_CONCURRENCY", "4"))))

    async def guarded(request):
        async with semaphore:
            return await _generate_validated(
                runtime=runtime, request=request, model_type=ContinuationCognitionOutput,
                max_repair_attempts=cognition_config.max_repair_attempts, module_id=module_id,
            )

    ordered_contexts = sorted(contexts.items, key=lambda item: (item.cycle_id, item.person_id, item.activation_id))
    async with asyncio.TaskGroup() as group:
        for context in ordered_contexts:
            tx = context.cognition_transaction_id
            if tx not in initial_by_tx or tx not in proposal_by_tx:
                raise S21InputError(
                    code="INITIAL_COGNITION_MISSING",
                    message="initial reading or preliminary belief is missing", module_id=module_id,
                    details={"cognition_transaction_id": tx},
                )
            request = _continuation_request(
                context=context, initial_reading=initial_by_tx[tx], preliminary_proposal=proposal_by_tx[tx],
                tool_results=tuple(tools_by_tx.get(tx, [])), social_intents=social_by_tx.get(tx, []),
                attention_intents=attention_by_tx.get(tx, []), cognition_config=cognition_config,
                provider=provider, runtime=runtime,
            )
            tasks[tx] = group.create_task(guarded(request))
    final_readings: list[AgentReadingRecord] = []
    final_proposals: list[RawBeliefProposalRecord] = []
    final_social: list = []
    final_attention: list = []
    contexts_by_tx = {item.cognition_transaction_id: item for item in contexts.items}
    for tx in sorted(tasks):
        output, response_hash = tasks[tx].result()
        context = contexts_by_tx[tx]
        _validate_belief_identity(
            output.final_belief, transaction_id=tx, person_id=context.person_id,
            as_of=context.as_of, module_id=module_id,
        )
        _validate_tool_citations(
            output=output, transaction_id=tx, validated_tool_results=validated_tool_results, module_id=module_id
        )
        final_readings.append(AgentReadingRecord(
            cognition_transaction_id=tx, person_id=context.person_id, stage=CognitionStage.CONTINUATION,
            summary=output.reading_summary, claims=output.claims, confidence=output.confidence,
            uncertainty=output.uncertainty, as_of=context.as_of, provider_id=provider.provider_id,
            model_id=provider.model_id, prompt_id=cognition_config.continuation_prompt_id,
            prompt_version=cognition_config.continuation_prompt_version, response_hash=response_hash,
        ))
        final_proposals.append(output.final_belief)
        final_social.extend(intent.model_copy(update={"status": IntentStatus.FINALIZED}) for intent in output.social_intents)
        final_attention.extend(output.attention_followups)
    return _continuation_panels(
        initial_readings=initial_readings, preliminary_proposals=preliminary_proposals,
        validated_tool_results=validated_tool_results, contexts=contexts, social_intents=social_intents,
        attention_intents=attention_intents, final_readings=final_readings, final_proposals=final_proposals,
        final_social=final_social, final_attention=final_attention, module_id=module_id,
    )


def _structured_payload(proposal: RawBeliefProposalRecord, definition, module_id: str):
    if definition.value_type == BeliefValueType.DIRECTIONAL_SCORE:
        direction = proposal.value_payload.get("direction")
        if not isinstance(direction, str) or direction not in definition.direction_mapping:
            raise S21ContractError(
                code="DIRECTION_MAPPING_INVALID",
                message="direction is absent from the proposition mapping", module_id=module_id,
            )
        return DirectionalBeliefPayload(
            value_type=BeliefValueType.DIRECTIONAL_SCORE, direction=direction,
            score=definition.direction_mapping[direction],
        )
    if definition.value_type == BeliefValueType.VOLATILITY_LEVEL:
        level = proposal.value_payload.get("level")
        if not isinstance(level, (int, float)) or isinstance(level, bool):
            raise S21ContractError(
                code="VOLATILITY_LEVEL_INVALID", message="volatility level must be numeric",
                module_id=module_id,
            )
        return VolatilityBeliefPayload(value_type=BeliefValueType.VOLATILITY_LEVEL, level=float(level))
    probabilities = proposal.value_payload.get("probabilities")
    if not isinstance(probabilities, dict):
        raise S21ContractError(
            code="REGIME_PROBABILITIES_INVALID", message="regime probabilities must be an object",
            module_id=module_id,
        )
    if set(probabilities) != set(definition.regime_labels):
        raise S21ContractError(
            code="REGIME_LABELS_INVALID",
            message="regime probability labels do not match the registry", module_id=module_id,
        )
    return RegimeBeliefPayload(
        value_type=BeliefValueType.REGIME_PROBABILITIES,
        probabilities={key: float(value) for key, value in probabilities.items()},
    )


def parse_structured_beliefs(
    *,
    raw_proposals: RawBeliefProposalPanel,
    proposition_registry: PropositionRegistryConfig,
) -> StructuredBeliefProposalPanel:
    """Implement P3.S21.M06 without validating evidence quality."""
    module_id = "P3.S21.M06"
    structured: list[StructuredBeliefProposalRecord] = []
    for proposal in sorted(
        raw_proposals.records,
        key=lambda item: (
            item.person_id,
            item.underlying_id,
            item.proposition_id,
            item.horizon,
            item.belief_proposal_id,
        ),
    ):
        try:
            definition = proposition_registry.get(proposal.proposition_id)
        except ValueError as exc:
            raise S21ContractError(
                code="UNKNOWN_PROPOSITION",
                message=str(exc),
                module_id=module_id,
            ) from exc
        if proposal.value_type != definition.value_type:
            raise S21ContractError(
                code="PROPOSITION_VALUE_TYPE_MISMATCH",
                message="belief value type does not match proposition registry",
                module_id=module_id,
            )
        if proposal.horizon not in definition.allowed_horizons:
            raise S21ContractError(
                code="HORIZON_NOT_ALLOWED",
                message="belief horizon is not allowed for this proposition",
                module_id=module_id,
            )
        if (
            proposal.underlying_id == "UNRESOLVED"
            and not definition.allow_unresolved_underlying
        ):
            raise S21ContractError(
                code="UNDERLYING_UNRESOLVED",
                message="this proposition requires a resolved underlying",
                module_id=module_id,
            )

        payload = _structured_payload(proposal, definition, module_id)

        structured.append(
            StructuredBeliefProposalRecord(
                belief_proposal_id=proposal.belief_proposal_id,
                cognition_transaction_id=proposal.cognition_transaction_id,
                person_id=proposal.person_id,
                underlying_id=proposal.underlying_id,
                proposition_id=proposal.proposition_id,
                horizon=proposal.horizon,
                payload=payload,
                strength=proposal.strength,
                confidence=proposal.confidence,
                uncertainty=proposal.uncertainty,
                supporting_evidence_refs=proposal.supporting_evidence_refs,
                opposing_evidence_refs=proposal.opposing_evidence_refs,
                generated_at=proposal.generated_at,
                as_of=proposal.as_of,
            )
        )

    return StructuredBeliefProposalPanel(
        status=(
            ArtifactStatus.READY if structured else ArtifactStatus.EMPTY_VALID
        ),
        records=tuple(structured),
        lineage=_lineage(
            module_id=module_id, source_lineages=[raw_proposals.lineage]
        ),
        reason_code=None if structured else "NO_BELIEF_PROPOSALS",
    )
