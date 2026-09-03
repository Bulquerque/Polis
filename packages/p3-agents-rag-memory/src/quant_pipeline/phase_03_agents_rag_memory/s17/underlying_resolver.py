from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from time import perf_counter

from pydantic import ValidationError

from .errors import InputContractError, ResolutionContractError
from .forbidden import reject_forbidden_fields
from .hashing import lineage_hash, sha256_hex
from .models import (
    EntityMapping,
    EntityUnderlyingMapConfig,
    ExecutionStatus,
    ExternalStimulusStream,
    IdentifierHint,
    ModuleMetrics,
    PropositionRegistry,
    PropositionStatus,
    ResolutionStatus,
    ResolvedExternalStimulusStream,
    ResolvedStimulusRecord,
    StimulusRecord,
    UnderlyingCandidate,
)

MODULE_ID = "P3.S17.M02"


class CanonicalUnderlyingResolver:
    """Resolve stimuli with explicit, versioned mappings and no ticker invention."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger(__name__)

    def resolve(
        self,
        *,
        stream: ExternalStimulusStream,
        mapping_config: EntityUnderlyingMapConfig,
        proposition_registry: PropositionRegistry,
    ) -> ResolvedExternalStimulusStream:
        started = perf_counter()
        self._emit("module_started", stream=stream, input_count=len(stream.items))
        indexes = _MappingIndexes.build(mapping_config, stream.as_of)
        propositions = {item.proposition_id: item for item in proposition_registry.propositions}

        items: list[ResolvedStimulusRecord] = []
        stream_warnings: list[str] = []
        unresolved_count = 0
        ambiguous_count = 0

        for stimulus in stream.items:
            candidates, method, warnings = indexes.resolve(stimulus, mapping_config)
            status, selected = _classify_resolution(candidates)
            if status is ResolutionStatus.UNRESOLVED:
                unresolved_count += 1
            elif status in {ResolutionStatus.AMBIGUOUS, ResolutionStatus.RESOLVED_MANY}:
                ambiguous_count += 1

            proposition_status, proposition_id, horizon, proposition_warnings = _resolve_proposition(
                stimulus,
                propositions,
            )
            warnings.extend(proposition_warnings)
            stream_warnings.extend(f"{stimulus.stimulus_id}:{warning}" for warning in warnings)

            item_payload = stimulus.model_dump()
            item_payload.update(
                {
                    "proposition_id": proposition_id,
                    "horizon": horizon,
                    "resolution_status": status,
                    "mapping_version": mapping_config.version,
                    "resolution_method": method,
                    "underlying_candidates": candidates,
                    "selected_underlying_id": selected,
                    "proposition_status": proposition_status,
                    "warnings": tuple(sorted(set(warnings))),
                }
            )
            items.append(ResolvedStimulusRecord(**item_payload))

        items.sort(key=lambda item: item.stimulus_id)
        if not items:
            output_status = ExecutionStatus.READY_EMPTY
        elif unresolved_count == len(items):
            output_status = ExecutionStatus.DEGRADED
        elif unresolved_count or ambiguous_count:
            output_status = ExecutionStatus.DEGRADED
        else:
            output_status = ExecutionStatus.READY

        base = {
            "schema_version": "resolved_external_stimulus_stream.v2",
            "contract_version": "p3.s17.v1",
            "run_id": stream.run_id,
            "cycle_id": stream.cycle_id,
            "target_cycle_id": stream.target_cycle_id,
            "as_of": stream.as_of,
            "items": tuple(items),
            "lineage_id": lineage_hash(
                stream.lineage_id,
                f"entity_map:{mapping_config.version}",
                f"proposition_registry:{proposition_registry.version}",
            ),
            "status": output_status,
            "warnings": tuple(sorted(set(stream_warnings))),
            "metrics": ModuleMetrics(
                input_record_count=len(stream.items),
                output_record_count=len(items),
                warning_count=len(set(stream_warnings)),
                unresolved_count=unresolved_count,
                ambiguous_count=ambiguous_count,
            ),
        }
        content_hash = sha256_hex(base)
        output = ResolvedExternalStimulusStream(content_hash=content_hash, **base)
        self._emit(
            "module_succeeded",
            stream=stream,
            input_count=len(stream.items),
            output_count=len(items),
            duration_ms=(perf_counter() - started) * 1000,
        )
        return output

    def _emit(
        self,
        event: str,
        *,
        stream: ExternalStimulusStream,
        input_count: int,
        output_count: int | None = None,
        duration_ms: float | None = None,
    ) -> None:
        self._logger.info(
            event,
            extra={
                "run_id": stream.run_id,
                "cycle_id": stream.cycle_id,
                "module_id": MODULE_ID,
                "as_of_time": stream.as_of.isoformat(),
                "input_record_count": input_count,
                "output_record_count": output_count,
                "duration_ms": duration_ms,
            },
        )


class _MappingIndexes:
    def __init__(
        self,
        *,
        by_entity: dict[str, list[EntityMapping]],
        by_alias: dict[str, list[EntityMapping]],
        by_identifier: dict[tuple[str, str, str | None, str | None], list[EntityMapping]],
    ) -> None:
        self.by_entity = by_entity
        self.by_alias = by_alias
        self.by_identifier = by_identifier

    @classmethod
    def build(cls, config: EntityUnderlyingMapConfig, as_of: datetime) -> _MappingIndexes:
        by_entity: dict[str, list[EntityMapping]] = defaultdict(list)
        by_alias: dict[str, list[EntityMapping]] = defaultdict(list)
        by_identifier: dict[tuple[str, str, str | None, str | None], list[EntityMapping]] = defaultdict(list)
        for mapping in config.mappings:
            if mapping.valid_from and as_of < mapping.valid_from:
                continue
            if mapping.valid_to and as_of > mapping.valid_to:
                continue
            if mapping.entity_id:
                by_entity[mapping.entity_id].append(mapping)
            for alias in mapping.aliases:
                by_alias[_normalize_text(alias)].append(mapping)
            for hint in mapping.identifiers:
                by_identifier[_identifier_key(hint)].append(mapping)
        return cls(
            by_entity=dict(by_entity),
            by_alias=dict(by_alias),
            by_identifier=dict(by_identifier),
        )

    def resolve(
        self,
        stimulus: StimulusRecord,
        config: EntityUnderlyingMapConfig,
    ) -> tuple[tuple[UnderlyingCandidate, ...], str, list[str]]:
        mappings: list[EntityMapping] = []
        methods: list[str] = []
        for entity_id in stimulus.entity_ids:
            found = self.by_entity.get(entity_id, [])
            if found:
                mappings.extend(found)
                methods.append("ENTITY_ID_EXACT")
        for hint in stimulus.identifier_hints:
            found = self.by_identifier.get(_identifier_key(hint), [])
            if found:
                mappings.extend(found)
                methods.append("IDENTIFIER_EXACT")
        if not mappings and config.allow_exact_subject_alias_match:
            found = self.by_alias.get(_normalize_text(stimulus.subject), [])
            if found:
                mappings.extend(found)
                methods.append("SUBJECT_ALIAS_EXACT")

        unique_mappings = {mapping.mapping_id: mapping for mapping in mappings}
        candidates_by_id: dict[str, UnderlyingCandidate] = {}
        warnings: list[str] = []
        for mapping in unique_mappings.values():
            for candidate in mapping.resolutions:
                existing = candidates_by_id.get(candidate.underlying_id)
                if existing is not None and existing != candidate:
                    raise ResolutionContractError(
                        module_id=MODULE_ID,
                        code="P3_S17_M02_OUTPUT_INVALID",
                        message="Conflicting candidates for the same underlying_id",
                        details={"underlying_id": candidate.underlying_id},
                    )
                candidates_by_id[candidate.underlying_id] = candidate

        candidates = tuple(sorted(candidates_by_id.values(), key=lambda item: item.underlying_id))
        if not candidates:
            warnings.append("UNDERLYING_UNRESOLVED")
            return (), "NO_MATCH", warnings
        method = "+".join(sorted(set(methods))) or "VERSIONED_MAPPING"
        if len(candidates) > 1:
            total = sum(candidate.weight for candidate in candidates)
            if abs(total - 1.0) > 1e-9:
                warnings.append("CANDIDATE_WEIGHTS_NOT_NORMALIZED")
                return candidates, method, warnings
            warnings.append("MULTIPLE_WEIGHTED_UNDERLYINGS")
        return candidates, method, warnings


def resolve_external_stimulus_stream(inputs: dict[str, object]) -> ResolvedExternalStimulusStream:
    reject_forbidden_fields(inputs, module_id=MODULE_ID)
    try:
        stream = ExternalStimulusStream.model_validate(inputs["external_stimulus_stream"])
        mapping_config = EntityUnderlyingMapConfig.model_validate(
            inputs["entity_underlying_map_config"]
        )
        proposition_registry = PropositionRegistry.model_validate(
            inputs["proposition_registry_config"]
        )
    except KeyError as exc:
        raise InputContractError(
            module_id=MODULE_ID,
            code="P3_S17_M02_INPUT_INVALID",
            message="Required input is missing",
            details={"input": str(exc)},
        ) from exc
    except ValidationError as exc:
        raise InputContractError(
            module_id=MODULE_ID,
            code="P3_S17_M02_INPUT_INVALID",
            message="Input contract validation failed",
            details={"errors": exc.errors(include_url=False)},
        ) from exc
    return CanonicalUnderlyingResolver().resolve(
        stream=stream,
        mapping_config=mapping_config,
        proposition_registry=proposition_registry,
    )


def _identifier_key(hint: IdentifierHint) -> tuple[str, str, str | None, str | None]:
    return (
        hint.id_type.upper(),
        hint.id_value.strip().upper(),
        hint.mic.upper() if hint.mic else None,
        hint.exchange_code.upper() if hint.exchange_code else None,
    )


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _classify_resolution(
    candidates: tuple[UnderlyingCandidate, ...],
) -> tuple[ResolutionStatus, str | None]:
    if not candidates:
        return ResolutionStatus.UNRESOLVED, None
    if len(candidates) == 1:
        return ResolutionStatus.RESOLVED_ONE, candidates[0].underlying_id
    total = sum(candidate.weight for candidate in candidates)
    if abs(total - 1.0) <= 1e-9:
        return ResolutionStatus.RESOLVED_MANY, None
    return ResolutionStatus.AMBIGUOUS, None


def _resolve_proposition(
    stimulus: StimulusRecord,
    propositions: dict[str, object],
) -> tuple[PropositionStatus, str | None, str | None, list[str]]:
    if stimulus.proposition_id is None:
        return PropositionStatus.UNRESOLVED, None, stimulus.horizon, ["PROPOSITION_UNRESOLVED"]
    definition = propositions.get(stimulus.proposition_id)
    if definition is None:
        return PropositionStatus.INVALID, stimulus.proposition_id, stimulus.horizon, [
            "PROPOSITION_UNKNOWN"
        ]
    allowed_horizons = getattr(definition, "allowed_horizons")
    horizon = stimulus.horizon or getattr(definition, "default_horizon")
    if horizon is None:
        return PropositionStatus.UNRESOLVED, stimulus.proposition_id, None, [
            "HORIZON_UNRESOLVED"
        ]
    if horizon not in allowed_horizons:
        return PropositionStatus.INVALID, stimulus.proposition_id, horizon, ["HORIZON_INVALID"]
    return PropositionStatus.RESOLVED, stimulus.proposition_id, horizon, []
