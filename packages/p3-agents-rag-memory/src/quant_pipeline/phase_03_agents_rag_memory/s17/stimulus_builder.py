from __future__ import annotations

from dataclasses import dataclass
import logging
from collections import defaultdict
from time import perf_counter
from typing import Any

from pydantic import ValidationError

from .errors import InputContractError, TemporalViolationError
from .forbidden import reject_forbidden_fields
from .hashing import lineage_hash, sha256_hex, stable_id
from .models import (
    ExecutionStatus,
    ExternalStimulusStream,
    GraphRagArtifact,
    ModuleMetrics,
    Phase3RunSnapshot,
    PitValidatedContext,
    RecordType,
    SalienceFeatures,
    StimulusBusConfig,
    StimulusOrigin,
    StimulusRecord,
)

MODULE_ID = "P3.S17.M01"


@dataclass(frozen=True, slots=True)
class _GraphIndexes:
    by_entity: dict[str, Any]
    exact_name: dict[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class _BuiltRecord:
    record: StimulusRecord
    warnings: tuple[str, ...]
    defaulted_component_count: int


class ExternalStimulusBuilder:
    """Build deterministic, PIT-safe external stimuli from canonical context records."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger(__name__)

    def build(
        self,
        *,
        pit_context: PitValidatedContext,
        graph: GraphRagArtifact,
        snapshot: Phase3RunSnapshot,
        config: StimulusBusConfig,
    ) -> ExternalStimulusStream:
        started = perf_counter()
        self._emit("module_started", snapshot=snapshot, input_count=len(pit_context.records))
        self._validate_graph(graph=graph, snapshot=snapshot)
        indexes = self._build_graph_indexes(graph=graph, config=config)

        built = [
            self._build_record(
                source=source,
                pit_context=pit_context,
                graph=graph,
                snapshot=snapshot,
                config=config,
                indexes=indexes,
            )
            for source in pit_context.records
        ]
        records = [item.record for item in built]
        self._ensure_unique_stimulus_ids(records)
        records.sort(key=lambda item: (item.available_at, item.source_event_id, item.stimulus_id))
        warnings = sorted({warning for item in built for warning in item.warnings})
        defaulted_count = sum(item.defaulted_component_count for item in built)
        output = self._build_stream(
            records=records,
            warnings=warnings,
            defaulted_count=defaulted_count,
            pit_context=pit_context,
            graph=graph,
            snapshot=snapshot,
        )
        self._emit(
            "module_succeeded",
            snapshot=snapshot,
            input_count=len(pit_context.records),
            output_count=len(records),
            duration_ms=(perf_counter() - started) * 1000,
        )
        return output

    @staticmethod
    def _validate_graph(*, graph: GraphRagArtifact, snapshot: Phase3RunSnapshot) -> None:
        if graph.as_of > snapshot.as_of:
            raise TemporalViolationError(
                module_id=MODULE_ID,
                code="P3_S17_M01_TEMPORAL_VIOLATION",
                message="Graph snapshot is later than the run snapshot",
                details={"graph_as_of": graph.as_of.isoformat(), "as_of": snapshot.as_of.isoformat()},
            )
        future_nodes = sorted(node.entity_id for node in graph.nodes if node.available_at > snapshot.as_of)
        if future_nodes:
            raise TemporalViolationError(
                module_id=MODULE_ID,
                code="P3_S17_M01_TEMPORAL_VIOLATION",
                message="Graph contains future entity nodes",
                details={"entity_ids": tuple(future_nodes)},
            )

    @staticmethod
    def _build_graph_indexes(
        *,
        graph: GraphRagArtifact,
        config: StimulusBusConfig,
    ) -> _GraphIndexes:
        by_entity = {node.entity_id: node for node in graph.nodes}
        raw_names: dict[str, list[str]] = defaultdict(list)
        if config.allow_exact_subject_graph_match:
            for node in graph.nodes:
                for name in (node.canonical_name, *node.aliases):
                    raw_names[_normalize_text(name)].append(node.entity_id)
        exact_name = {
            name: tuple(sorted(set(entity_ids)))
            for name, entity_ids in raw_names.items()
        }
        return _GraphIndexes(by_entity=by_entity, exact_name=exact_name)

    def _build_record(
        self,
        *,
        source: Any,
        pit_context: PitValidatedContext,
        graph: GraphRagArtifact,
        snapshot: Phase3RunSnapshot,
        config: StimulusBusConfig,
        indexes: _GraphIndexes,
    ) -> _BuiltRecord:
        self._validate_source(source=source, snapshot=snapshot, config=config)
        stimulus_type = source.stimulus_type or config.stimulus_type_by_record_type[source.record_type]
        features, defaulted = self._resolve_features(source.record_type, source.salience_features, config)
        salience = _calculate_salience(features, config)
        entity_ids, graph_evidence_refs, identifier_hints, warnings = self._resolve_graph_context(
            source=source,
            indexes=indexes,
            allow_exact_match=config.allow_exact_subject_graph_match,
        )
        record = StimulusRecord(
            stimulus_id=stable_id(
                "stim",
                snapshot.run_id,
                snapshot.cycle_id,
                source.source_event_id,
                source.available_at,
                source.content_hash,
            ),
            origin_type=StimulusOrigin.EXTERNAL_PIT_CONTEXT,
            record_id=source.record_id,
            record_type=source.record_type,
            source_event_id=source.source_event_id,
            causal_parent_id=None,
            created_cycle_id=snapshot.cycle_id,
            target_cycle_id=snapshot.target_cycle_id or snapshot.cycle_id,
            event_time=source.event_time,
            available_at=source.available_at,
            subject=source.subject,
            stimulus_type=stimulus_type,
            intensity=salience,
            salience=salience,
            salience_features=features,
            salience_formula_id=config.salience_formula_id,
            defaulted_components=defaulted,
            entity_ids=tuple(sorted(set(entity_ids))),
            identifier_hints=tuple(_deduplicate_identifier_hints(identifier_hints)),
            proposition_id=source.proposition_id,
            horizon=source.horizon,
            content_hash=source.content_hash,
            evidence_refs=source.evidence_refs,
            graph_evidence_refs=tuple(sorted(set(graph_evidence_refs))),
            lineage_id=lineage_hash(
                pit_context.lineage_id,
                graph.lineage_id,
                snapshot.lineage_id,
                source.lineage_id,
            ),
        )
        return _BuiltRecord(
            record=record,
            warnings=tuple(warnings),
            defaulted_component_count=len(defaulted),
        )

    @staticmethod
    def _validate_source(*, source: Any, snapshot: Phase3RunSnapshot, config: StimulusBusConfig) -> None:
        if source.available_at > snapshot.as_of:
            raise TemporalViolationError(
                module_id=MODULE_ID,
                code="P3_S17_M01_TEMPORAL_VIOLATION",
                message="Context record is not available at run as_of",
                details={
                    "record_id": source.record_id,
                    "available_at": source.available_at.isoformat(),
                    "as_of": snapshot.as_of.isoformat(),
                },
            )
        if len(source.subject) > config.max_subject_length:
            raise InputContractError(
                module_id=MODULE_ID,
                code="P3_S17_M01_INPUT_INVALID",
                message="Context subject exceeds configured length",
                details={"record_id": source.record_id, "length": len(source.subject)},
            )

    @staticmethod
    def _resolve_graph_context(
        *,
        source: Any,
        indexes: _GraphIndexes,
        allow_exact_match: bool,
    ) -> tuple[list[str], list[str], list[Any], list[str]]:
        warnings: list[str] = []
        entity_ids = list(source.entity_ids)
        if not entity_ids and allow_exact_match:
            matches = indexes.exact_name.get(_normalize_text(source.subject), ())
            if len(matches) == 1:
                entity_ids.append(matches[0])
            elif len(matches) > 1:
                warnings.append(f"AMBIGUOUS_GRAPH_SUBJECT_MATCH:{source.record_id}")

        evidence_refs: list[str] = []
        identifier_hints = list(source.identifier_hints)
        for entity_id in entity_ids:
            node = indexes.by_entity.get(entity_id)
            if node is None:
                warnings.append(f"GRAPH_ENTITY_NOT_FOUND:{source.record_id}:{entity_id}")
                continue
            evidence_refs.extend(node.evidence_refs)
            identifier_hints.extend(node.identifier_hints)
        return entity_ids, evidence_refs, identifier_hints, warnings

    @staticmethod
    def _ensure_unique_stimulus_ids(records: list[StimulusRecord]) -> None:
        seen: set[str] = set()
        for record in records:
            if record.stimulus_id in seen:
                raise InputContractError(
                    module_id=MODULE_ID,
                    code="P3_S17_M01_INPUT_INVALID",
                    message="Duplicate external stimulus identity",
                    details={"stimulus_id": record.stimulus_id, "record_id": record.record_id},
                )
            seen.add(record.stimulus_id)

    @staticmethod
    def _build_stream(
        *,
        records: list[StimulusRecord],
        warnings: list[str],
        defaulted_count: int,
        pit_context: PitValidatedContext,
        graph: GraphRagArtifact,
        snapshot: Phase3RunSnapshot,
    ) -> ExternalStimulusStream:
        base = {
            "schema_version": "external_stimulus_stream.v2",
            "contract_version": "p3.s17.v1",
            "run_id": snapshot.run_id,
            "cycle_id": snapshot.cycle_id,
            "target_cycle_id": snapshot.target_cycle_id or snapshot.cycle_id,
            "as_of": snapshot.as_of,
            "items": tuple(records),
            "lineage_id": lineage_hash(
                pit_context.lineage_id,
                graph.lineage_id,
                snapshot.lineage_id,
            ),
            "status": ExecutionStatus.READY if records else ExecutionStatus.READY_EMPTY,
            "warnings": tuple(warnings),
            "metrics": ModuleMetrics(
                input_record_count=len(pit_context.records),
                output_record_count=len(records),
                warning_count=len(warnings),
                defaulted_component_count=defaulted_count,
            ),
        }
        return ExternalStimulusStream(content_hash=sha256_hex(base), **base)

    @staticmethod
    def _resolve_features(
        record_type: RecordType,
        supplied: SalienceFeatures | None,
        config: StimulusBusConfig,
    ) -> tuple[SalienceFeatures, tuple[str, ...]]:
        if supplied is not None:
            return supplied, ()
        return config.salience_defaults_by_record_type[record_type], (
            "source_quality",
            "novelty",
            "subject_relevance",
            "event_severity",
            "information_specificity",
        )

    def _emit(
        self,
        event: str,
        *,
        snapshot: Phase3RunSnapshot,
        input_count: int,
        output_count: int | None = None,
        duration_ms: float | None = None,
    ) -> None:
        self._logger.info(
            event,
            extra={
                "run_id": snapshot.run_id,
                "cycle_id": snapshot.cycle_id,
                "module_id": MODULE_ID,
                "as_of_time": snapshot.as_of.isoformat(),
                "input_record_count": input_count,
                "output_record_count": output_count,
                "duration_ms": duration_ms,
            },
        )


def build_external_stimulus_stream(inputs: dict[str, object]) -> ExternalStimulusStream:
    reject_forbidden_fields(inputs, module_id=MODULE_ID)
    try:
        pit_context = PitValidatedContext.model_validate(inputs["pit_validated_context"])
        graph = GraphRagArtifact.model_validate(inputs["graph_rag_artifact"])
        snapshot = Phase3RunSnapshot.model_validate(inputs["phase3_run_snapshot"])
        config = StimulusBusConfig.model_validate(inputs["stimulus_bus_config"])
    except KeyError as exc:
        raise InputContractError(
            module_id=MODULE_ID,
            code="P3_S17_M01_INPUT_INVALID",
            message="Required input is missing",
            details={"input": str(exc)},
        ) from exc
    except ValidationError as exc:
        raise InputContractError(
            module_id=MODULE_ID,
            code="P3_S17_M01_INPUT_INVALID",
            message="Input contract validation failed",
            details={"errors": exc.errors(include_url=False)},
        ) from exc
    return ExternalStimulusBuilder().build(
        pit_context=pit_context,
        graph=graph,
        snapshot=snapshot,
        config=config,
    )


def _calculate_salience(features: SalienceFeatures, config: StimulusBusConfig) -> float:
    weights = config.salience_weights
    value = (
        features.source_quality * weights.source_quality
        + features.novelty * weights.novelty
        + features.subject_relevance * weights.subject_relevance
        + features.event_severity * weights.event_severity
        + features.information_specificity * weights.information_specificity
    )
    return round(max(0.0, min(1.0, value)), 12)


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _deduplicate_identifier_hints(items: list[object]) -> list[object]:
    seen: set[tuple[object, ...]] = set()
    result: list[object] = []
    for item in items:
        key = (
            getattr(item, "id_type"),
            getattr(item, "id_value"),
            getattr(item, "mic"),
            getattr(item, "exchange_code"),
            getattr(item, "currency"),
        )
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
