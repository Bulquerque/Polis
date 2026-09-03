"""Implementation of P3.S5.M01 personality_candidate_generator."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from time import monotonic
from typing import Callable

from pydantic import ValidationError

from .errors import NonRetryableProviderError, ProviderOutputError, RetryableProviderError
from .hashing import sha256_hex, stable_short_id
from .models import (
    AttemptStatus,
    CandidateBatchProposal,
    CandidateRecord,
    GenerationAttemptAudit,
    GenerationRequest,
    GenerationResult,
    PersonalityCandidatePool,
    PersonalityCreatorGenerationAudit,
)
from .ports import ProviderMessage, StructuredGenerationRequest, StructuredLLMPort

Sleep = Callable[[float], object]

@dataclass(frozen=True, slots=True)
class PromptAsset:
    prompt_id: str
    prompt_version: str
    content: str

    @property
    def content_hash(self) -> str:
        return sha256_hex(self.content.encode())

class PersonalityCandidateGenerator:
    """Generate candidates via a provider port; never create fallback candidates."""

    MODULE_ID = "P3.S5.M01"
    FORBIDDEN_FIELDS = frozenset(
        {
            "future_return",
            "candidate_score",
            "rank_score",
            "portfolio_weight",
            "trade_decision",
            "buy_sell_signal",
        }
    )

    def __init__(
        self,
        provider: StructuredLLMPort,
        prompt: PromptAsset,
        sleep: Callable[[float], object] = asyncio.sleep,
    ) -> None:
        self._provider = provider
        self._prompt = prompt
        self._sleep = sleep

    async def execute(self, request: GenerationRequest) -> GenerationResult:
        self._validate_prompt_binding(request)
        schema = CandidateBatchProposal.model_json_schema()
        provider_request = self._build_provider_request(request, schema, repair_message=None)
        attempts: list[GenerationAttemptAudit] = []
        proposal: CandidateBatchProposal | None = None
        final_response_hash: str | None = None
        schema_repairs = 0

        for attempt_number in range(1, request.retry_policy.max_provider_attempts + 1):
            started = monotonic()
            try:
                response = await self._provider.generate_structured(provider_request)
                final_response_hash = sha256_hex(response.content.encode())
                proposal = self._parse_and_validate_response(
                    response.content,
                    request,
                )
                attempts.append(
                    GenerationAttemptAudit(
                        attempt_number=attempt_number,
                        status=AttemptStatus.SUCCEEDED,
                        provider_id=request.provider_adapter_registry_config.selected_provider().provider_id,
                        provider_kind=request.provider_adapter_registry_config.selected_provider().provider_kind,
                        model_id=request.provider_adapter_registry_config.selected_provider().model_id,
                        request_hash=provider_request.request_hash,
                        response_hash=final_response_hash,
                        provider_request_id=response.provider_request_id,
                        cache_hit=response.cache_hit,
                        duration_ms=max(0, round((monotonic() - started) * 1000)),
                        usage=response.usage,
                    )
                )
                break
            except ProviderOutputError as exc:
                attempts.append(
                    self._failed_attempt(
                        request,
                        provider_request,
                        attempt_number,
                        AttemptStatus.INVALID_STRUCTURED_OUTPUT,
                        started,
                        "P3_S5_M01_INVALID_STRUCTURED_OUTPUT",
                        str(exc),
                        final_response_hash,
                    )
                )
                if schema_repairs >= request.retry_policy.max_schema_repair_attempts:
                    raise
                schema_repairs += 1
                provider_request = self._build_provider_request(
                    request,
                    schema,
                    repair_message=str(exc),
                )
            except RetryableProviderError as exc:
                attempts.append(
                    self._failed_attempt(
                        request,
                        provider_request,
                        attempt_number,
                        AttemptStatus.RETRYABLE_FAILURE,
                        started,
                        "P3_S5_M01_RETRYABLE_PROVIDER_FAILURE",
                        str(exc),
                        None,
                    )
                )
                if attempt_number >= request.retry_policy.max_provider_attempts:
                    raise
                await self._sleep(self._backoff_seconds(request, attempt_number))
            except NonRetryableProviderError as exc:
                attempts.append(
                    self._failed_attempt(
                        request,
                        provider_request,
                        attempt_number,
                        AttemptStatus.NON_RETRYABLE_FAILURE,
                        started,
                        "P3_S5_M01_NON_RETRYABLE_PROVIDER_FAILURE",
                        str(exc),
                        None,
                    )
                )
                raise

        if proposal is None or final_response_hash is None:
            raise RetryableProviderError("provider attempts exhausted without valid candidates")

        records = self._materialize_records(
            proposal,
            request,
            provider_request.request_hash,
            final_response_hash,
        )
        lineage_id = stable_short_id(
            "lin",
            {
                "module_id": self.MODULE_ID,
                "run_id": request.run_context.run_id,
                "round": request.run_context.generation_round,
                "candidate_ids": [record.candidate_id for record in records],
            },
        )
        pool = PersonalityCandidatePool(
            run_id=request.run_context.run_id,
            snapshot_id=request.run_context.snapshot_id,
            creator_run_id=request.run_context.creator_run_id,
            generation_round=request.run_context.generation_round,
            generation_mode=request.prior_population_generation_state.mode,
            candidates=records,
            lineage_id=lineage_id,
        )
        audit = PersonalityCreatorGenerationAudit(
            run_id=request.run_context.run_id,
            snapshot_id=request.run_context.snapshot_id,
            creator_run_id=request.run_context.creator_run_id,
            prompt_id=self._prompt.prompt_id,
            prompt_version=self._prompt.prompt_version,
            prompt_hash=self._prompt.content_hash,
            seed=request.run_context.seed,
            generation_round=request.run_context.generation_round,
            generation_mode=request.prior_population_generation_state.mode,
            attempts=tuple(attempts),
            final_status=AttemptStatus.SUCCEEDED,
            generated_candidate_count=len(records),
            lineage_id=stable_short_id("lin", {"pool": lineage_id, "type": "generation_audit"}),
        )
        return GenerationResult(
            personality_candidate_pool=pool,
            personality_creator_generation_audit=audit,
        )

    def _validate_prompt_binding(self, request: GenerationRequest) -> None:
        config = request.population_generation_config
        if config.prompt_id != self._prompt.prompt_id:
            raise ProviderOutputError("configured prompt_id does not match loaded prompt")
        if config.prompt_version != self._prompt.prompt_version:
            raise ProviderOutputError("configured prompt_version does not match loaded prompt")
        if not request.provider_adapter_registry_config.selected_provider().supports_strict_json_schema:
            raise ProviderOutputError("selected provider/model is not qualified for strict JSON Schema")

    def _build_provider_request(
        self,
        request: GenerationRequest,
        schema: dict[str, object],
        repair_message: str | None,
    ) -> StructuredGenerationRequest:
        state = request.prior_population_generation_state
        registry = request.personality_tag_registry
        policy = request.person_schema_policy
        config = request.population_generation_config
        payload = {
            "mode": state.mode.value,
            "requested_batch_size": config.requested_batch_size,
            "missing_coverage_cells": list(state.missing_coverage_cells),
            "density_targets": list(state.density_targets),
            # The registry is the universe of tags, but the person policy is
            # the authority for this generation request. Sending the broader
            # registry caused valid registry tags to be rejected by S5.M02.
            "allowed_tag_ids": sorted(policy.allowed_tag_ids),
            "roles": [role.model_dump(mode="json") for role in policy.roles],
            "required_role_families": list(config.required_role_families),
            "objective_dimensions": list(policy.objective_dimensions),
            "experience_bands": [band.model_dump(mode="json") for band in policy.experience_bands],
            "education_levels": sorted(policy.education_rank),
            "forbidden_fields": sorted(self.FORBIDDEN_FIELDS),
        }
        messages = [
            ProviderMessage(role="system", content=self._prompt.content),
            ProviderMessage(role="user", content=json.dumps(payload, sort_keys=True)),
        ]
        if repair_message:
            messages.append(
                ProviderMessage(
                    role="user",
                    content=(
                        "The previous response failed local validation. Return a completely new "
                        f"response matching the schema. Validation summary: {repair_message[:1000]}"
                    ),
                )
            )
        request_hash = sha256_hex(
            {
                "provider_id": request.provider_adapter_registry_config.selected_provider().provider_id,
                "model_id": request.provider_adapter_registry_config.selected_provider().model_id,
                "messages": [message.model_dump(mode="json") for message in messages],
                "schema": schema,
                "temperature": config.creator_temperature,
                "max_output_tokens": config.max_output_tokens,
                "seed": request.run_context.seed,
            }
        )
        return StructuredGenerationRequest(
            provider_id=request.provider_adapter_registry_config.selected_provider().provider_id,
            provider_kind=request.provider_adapter_registry_config.selected_provider().provider_kind,
            model_id=request.provider_adapter_registry_config.selected_provider().model_id,
            messages=tuple(messages),
            json_schema_name="P3S5CandidateBatchProposal",
            json_schema=schema,
            temperature=config.creator_temperature,
            max_output_tokens=config.max_output_tokens,
            seed=request.run_context.seed,
            request_hash=request_hash,
        )

    def _parse_and_validate_response(
        self,
        content: str,
        request: GenerationRequest,
    ) -> CandidateBatchProposal:
        try:
            proposal = CandidateBatchProposal.model_validate_json(content)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ProviderOutputError(str(exc)) from exc
        expected = request.population_generation_config.requested_batch_size
        if len(proposal.candidates) != expected:
            raise ProviderOutputError(
                f"provider returned {len(proposal.candidates)} candidates; expected {expected}"
            )
        allowed_tags = request.personality_tag_registry.tag_ids()
        allowed_objectives = frozenset(request.person_schema_policy.objective_dimensions)
        role_map = request.person_schema_policy.role_map()
        for candidate in proposal.candidates:
            unknown_tags = {tag.tag_id for tag in candidate.tags} - allowed_tags
            unknown_objectives = {
                item.objective_id for item in candidate.objective_weights
            } - allowed_objectives
            if unknown_tags:
                raise ProviderOutputError(f"unknown tags: {sorted(unknown_tags)}")
            if unknown_objectives:
                raise ProviderOutputError(f"unknown objectives: {sorted(unknown_objectives)}")
            role = role_map.get(candidate.economic_role)
            if role is None:
                raise ProviderOutputError(f"unknown economic_role: {candidate.economic_role}")
            if candidate.role_family != role.role_family:
                raise ProviderOutputError("role_family does not match economic_role")
        return proposal

    def _materialize_records(
        self,
        proposal: CandidateBatchProposal,
        request: GenerationRequest,
        request_hash: str,
        response_hash: str,
    ) -> tuple[CandidateRecord, ...]:
        records = []
        seen: set[str] = set()
        for profile in proposal.candidates:
            identity_payload = {
                "creator_run_id": request.run_context.creator_run_id,
                "generation_round": request.run_context.generation_round,
                "profile": profile.model_dump(mode="json"),
            }
            candidate_id = stable_short_id("cand", identity_payload)
            if candidate_id in seen:
                raise ProviderOutputError("provider returned duplicate candidate profiles")
            seen.add(candidate_id)
            records.append(
                CandidateRecord(
                    candidate_id=candidate_id,
                    profile=profile,
                    creator_run_id=request.run_context.creator_run_id,
                    generation_round=request.run_context.generation_round,
                    generation_mode=request.prior_population_generation_state.mode,
                    provider_id=request.provider_adapter_registry_config.selected_provider().provider_id,
                    model_id=request.provider_adapter_registry_config.selected_provider().model_id,
                    prompt_id=self._prompt.prompt_id,
                    prompt_version=self._prompt.prompt_version,
                    prompt_hash=self._prompt.content_hash,
                    request_hash=request_hash,
                    response_hash=response_hash,
                    lineage_id=stable_short_id("lin", {"candidate_id": candidate_id}),
                )
            )
        return tuple(records)

    def _failed_attempt(
        self,
        request: GenerationRequest,
        provider_request: StructuredGenerationRequest,
        attempt_number: int,
        status: AttemptStatus,
        started: float,
        error_code: str,
        message: str,
        response_hash: str | None,
    ) -> GenerationAttemptAudit:
        return GenerationAttemptAudit(
            attempt_number=attempt_number,
            status=status,
            provider_id=request.provider_adapter_registry_config.selected_provider().provider_id,
            provider_kind=request.provider_adapter_registry_config.selected_provider().provider_kind,
            model_id=request.provider_adapter_registry_config.selected_provider().model_id,
            request_hash=provider_request.request_hash,
            response_hash=response_hash,
            cache_hit=False,
            duration_ms=max(0, round((monotonic() - started) * 1000)),
            error_code=error_code,
            error_message=message[:1000],
        )

    @staticmethod
    def _backoff_seconds(request: GenerationRequest, attempt_number: int) -> float:
        retry = request.retry_policy
        return min(
            retry.maximum_backoff_seconds,
            retry.initial_backoff_seconds * (2 ** max(0, attempt_number - 1)),
        )
