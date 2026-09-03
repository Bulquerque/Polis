from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from pydantic import ValidationError

from .errors import MemoryIndexError, MemoryIndexStoreError, S14Issue
from .hashing import hash_value, stable_id
from .models import (
    ArtifactStatus,
    CurrentMemoryState,
    ExclusionSummary,
    FutureRecordPolicy,
    IndexEntry,
    IndexMode,
    IndexPartitionRequest,
    MemoryAccessPolicy,
    MemoryIndexManifest,
    MemoryIndexPartition,
    MemoryRecord,
    RetrievalConfig,
    VisibilityScope,
)
from .ports import MemoryIndexPort

Logger = Callable[[str, dict[str, object]], None]


def _log(logger: Logger | None, event: str, **fields: object) -> None:
    if logger is not None:
        logger(event, fields)


@dataclass(frozen=True, slots=True)
class ParsedMemoryIndexInputs:
    state: CurrentMemoryState
    policy: MemoryAccessPolicy
    config: RetrievalConfig


@dataclass(frozen=True, slots=True)
class MemoryIndexInputParser:
    def parse(self, *, current_memory_state: object, memory_access_policy: object, retrieval_config: object) -> ParsedMemoryIndexInputs:
        try:
            state = current_memory_state if isinstance(current_memory_state, CurrentMemoryState) else CurrentMemoryState.model_validate(current_memory_state)
            policy = memory_access_policy if isinstance(memory_access_policy, MemoryAccessPolicy) else MemoryAccessPolicy.model_validate(memory_access_policy)
            config = retrieval_config if isinstance(retrieval_config, RetrievalConfig) else RetrievalConfig.model_validate(retrieval_config)
        except (ValidationError, TypeError, ValueError) as exc:
            raise MemoryIndexError(
                [S14Issue(code="P3_S14_M02_INPUT_INVALID", message="P3.S14.M02 input validation failed.", details={"error": str(exc)})]
            ) from exc
        return ParsedMemoryIndexInputs(state=state, policy=policy, config=config)


@dataclass(frozen=True, slots=True)
class MemoryIndexCompatibilityValidator:
    def validate(self, parsed: ParsedMemoryIndexInputs) -> None:
        state, policy, config = parsed.state, parsed.policy, parsed.config
        if state.run_id != policy.run_id or state.snapshot_id != policy.snapshot_id:
            raise MemoryIndexError([S14Issue(code="P3_S14_M02_IDENTITY_MISMATCH", message="Memory state and policy must share run_id and snapshot_id.")])
        if state.as_of_time != policy.as_of_time:
            raise MemoryIndexError([S14Issue(code="P3_S14_M02_AS_OF_MISMATCH", message="Memory state and policy must share the same as_of_time.")])
        if len(state.records) > config.max_records:
            raise MemoryIndexError([S14Issue(code="P3_S14_M02_MAX_RECORDS_EXCEEDED", message="Memory state exceeds the configured index record cap.")])


@dataclass(frozen=True, slots=True)
class MemorySelection:
    included: tuple[MemoryRecord, ...]
    future: tuple[str, ...]
    audit_only: tuple[str, ...]
    disabled: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MemoryRecordSelector:
    def select(self, parsed: ParsedMemoryIndexInputs) -> MemorySelection:
        state, policy = parsed.state, parsed.policy
        type_policy = {row.memory_type: row for row in policy.type_policies}
        scope_policy = {row.visibility_scope: row for row in policy.scope_policies}
        included: list[MemoryRecord] = []
        future: list[str] = []
        audit_only: list[str] = []
        disabled: list[str] = []
        seen: set[str] = set()
        ordered = sorted(
            state.records,
            key=lambda row: (
                row.person_id,
                row.memory_type.value,
                row.visibility_scope.value,
                row.available_at,
                row.memory_id,
            ),
        )
        for record in ordered:
            if record.memory_id in seen:
                raise MemoryIndexError([S14Issue(code="P3_S14_M02_DUPLICATE_MEMORY_ID", message="Duplicate memory_id detected.", path=record.memory_id)])
            seen.add(record.memory_id)
            if record.available_at > state.as_of_time:
                future.append(record.memory_id)
            elif record.visibility_scope is VisibilityScope.AUDIT_ONLY:
                audit_only.append(record.memory_id)
            elif not type_policy[record.memory_type].enabled or not scope_policy[record.visibility_scope].retrievable:
                disabled.append(record.memory_id)
            else:
                included.append(record)
        if future and policy.temporal_policy.future_record_policy is FutureRecordPolicy.BLOCK:
            raise MemoryIndexError([
                S14Issue(
                    code="P3_S14_M02_FUTURE_MEMORY_BLOCKED",
                    message="Future memory encountered under BLOCK policy.",
                    details={"memory_ids": future},
                )
            ])
        return MemorySelection(tuple(included), tuple(future), tuple(audit_only), tuple(disabled))


@dataclass(frozen=True, slots=True)
class MemoryIndexPartitionBuilder:
    index_port: MemoryIndexPort

    def build(self, selection: MemorySelection) -> tuple[MemoryIndexPartition, ...]:
        raw: dict[tuple[str, str, str], list[MemoryRecord]] = {}
        for record in selection.included:
            key = (record.person_id, record.memory_type.value, record.visibility_scope.value)
            raw.setdefault(key, []).append(record)
        partitions: list[MemoryIndexPartition] = []
        for (person_id, memory_type, visibility_scope), records in sorted(raw.items()):
            entries = tuple(
                IndexEntry(
                    memory_id=row.memory_id,
                    person_id=row.person_id,
                    memory_type=row.memory_type,
                    visibility_scope=row.visibility_scope,
                    available_at=row.available_at,
                    content_ref=row.content_ref,
                    importance=row.importance,
                    repetition=row.repetition,
                    significance=row.significance,
                )
                for row in records
            )
            partition_key = f"person={person_id}/type={memory_type}/scope={visibility_scope}"
            partition_hash = hash_value(entries)
            request = IndexPartitionRequest(partition_key=partition_key, entries=entries, partition_hash=partition_hash)
            try:
                built = self.index_port.build_partition(request)
            except MemoryIndexStoreError:
                raise
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                raise MemoryIndexStoreError([
                    S14Issue(code="P3_S14_M02_INDEX_BUILD_FAILED", message="Memory index adapter failed.", details={"error": str(exc)})
                ]) from exc
            if built.partition_hash != partition_hash or built.record_count != len(entries):
                raise MemoryIndexError([S14Issue(code="P3_S14_M02_ADAPTER_CONTRACT_VIOLATION", message="Index adapter returned inconsistent partition metadata.")])
            partitions.append(
                MemoryIndexPartition(
                    partition_key=partition_key,
                    person_id=person_id,
                    memory_type=memory_type,
                    visibility_scope=visibility_scope,
                    record_count=len(entries),
                    partition_hash=partition_hash,
                    index_ref=built.index_ref,
                    storage_hash=built.storage_hash,
                    retrievable=True,
                )
            )
        return tuple(partitions)


@dataclass(frozen=True, slots=True)
class MemoryIndexManifestAssembler:
    def assemble(
        self,
        parsed: ParsedMemoryIndexInputs,
        selection: MemorySelection,
        partitions: tuple[MemoryIndexPartition, ...],
    ) -> MemoryIndexManifest:
        state, policy, config = parsed.state, parsed.policy, parsed.config
        excluded_ids = sorted((*selection.future, *selection.audit_only, *selection.disabled))
        exclusions = ExclusionSummary(
            future_record_count=len(selection.future),
            audit_only_record_count=len(selection.audit_only),
            disabled_type_record_count=len(selection.disabled),
            excluded_memory_ids_hash=hash_value(excluded_ids),
        )
        status = ArtifactStatus.DEGRADED if excluded_ids else ArtifactStatus.READY if selection.included else ArtifactStatus.EMPTY_VALID
        mode = IndexMode.GENESIS if not state.records else IndexMode.REFRESH
        retrieval_config_hash = hash_value(config)
        core = {
            "run_id": state.run_id,
            "snapshot_id": state.snapshot_id,
            "cycle_id": state.cycle_id,
            "cycle_number": state.cycle_number,
            "as_of_time": state.as_of_time,
            "mode": mode,
            "memory_state_hash": state.content_hash,
            "policy_hash": policy.content_hash,
            "retrieval_config_hash": retrieval_config_hash,
            "adapter_id": config.adapter_id,
            "adapter_version": config.adapter_version,
            "index_version": config.index_version,
            "partitions": partitions,
            "total_input_records": len(state.records),
            "total_indexed_records": len(selection.included),
            "exclusions": exclusions,
            "status": status,
        }
        content_hash = hash_value(core)
        return MemoryIndexManifest(
            artifact_id=stable_id("memory-index-manifest", state.run_id, state.cycle_id, content_hash),
            module_id="P3.S14.M02",
            run_id=state.run_id,
            snapshot_id=state.snapshot_id,
            cycle_id=state.cycle_id,
            cycle_number=state.cycle_number,
            as_of_time=state.as_of_time,
            mode=mode,
            memory_state_hash=state.content_hash,
            policy_hash=policy.content_hash,
            retrieval_config_hash=retrieval_config_hash,
            adapter_id=config.adapter_id,
            adapter_version=config.adapter_version,
            index_version=config.index_version,
            partitions=partitions,
            total_input_records=len(state.records),
            total_indexed_records=len(selection.included),
            exclusions=exclusions,
            status=status,
            content_hash=content_hash,
            lineage_id=stable_id("lineage-memory-index", state.lineage_id, policy.lineage_id, content_hash),
        )


@dataclass(frozen=True, slots=True)
class MemoryIndexPlanner:
    index_port: MemoryIndexPort
    logger: Logger | None = None
    parser: MemoryIndexInputParser = MemoryIndexInputParser()
    validator: MemoryIndexCompatibilityValidator = MemoryIndexCompatibilityValidator()
    selector: MemoryRecordSelector = MemoryRecordSelector()
    assembler: MemoryIndexManifestAssembler = MemoryIndexManifestAssembler()

    def build(self, **inputs: object) -> MemoryIndexManifest:
        _log(self.logger, "module_started", module_id="P3.S14.M02")
        parsed = self.parser.parse(**inputs)
        self.validator.validate(parsed)
        selection = self.selector.select(parsed)
        partitions = MemoryIndexPartitionBuilder(self.index_port).build(selection)
        result = self.assembler.assemble(parsed, selection, partitions)
        _log(
            self.logger,
            "module_succeeded",
            module_id="P3.S14.M02",
            run_id=result.run_id,
            cycle_id=result.cycle_id,
            status=result.status.value,
            input_record_count=result.total_input_records,
            output_record_count=result.total_indexed_records,
            warning_count=(
                result.exclusions.future_record_count
                + result.exclusions.audit_only_record_count
                + result.exclusions.disabled_type_record_count
            ),
        )
        return result
