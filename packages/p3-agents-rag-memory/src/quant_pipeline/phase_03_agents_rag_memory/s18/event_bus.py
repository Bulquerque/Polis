from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from .errors import (
    S18DuplicateConflictError,
    S18HashMismatchError,
    S18InputError,
    S18TemporalViolationError,
)
from .forbidden import reject_forbidden_fields
from .hashing import deterministic_id, hash_without_field, normalized_subject, sha256_hex
from .models import (
    EndogenousStimulusRecord,
    EndogenousStimulusStream,
    EventBusMetrics,
    ExecutionStatus,
    PanelAdmissionDecision,
    PanelDecisionReason,
    PropositionStatus,
    ResolvedExternalStimulusRecord,
    ResolvedExternalStimulusStreamInput,
    ResolutionStatus,
    StimulusBusConfig,
    StimulusOrigin,
    StimulusPanel,
    StimulusPanelRecord,
)

REQUIRED_INPUTS = (
    "resolved_external_stimulus_stream",
    "endogenous_stimulus_stream",
    "stimulus_event_bus_config",
)


def merge_stimulus_event_bus(inputs: Mapping[str, Any]) -> StimulusPanel:
    """Merge external and endogenous streams deterministically and apply admission budgets."""

    reject_forbidden_fields(inputs)
    _require_inputs(inputs)
    try:
        external = ResolvedExternalStimulusStreamInput.model_validate(
            inputs["resolved_external_stimulus_stream"]
        )
        endogenous = EndogenousStimulusStream.model_validate(inputs["endogenous_stimulus_stream"])
        config = StimulusBusConfig.model_validate(inputs["stimulus_event_bus_config"])
    except ValidationError as exc:
        raise S18InputError(f"P3.S18.M02 input validation failed: {exc}") from exc

    _validate_streams(external, endogenous, config)
    raw_records = [
        *(_from_external(item, config) for item in external.items),
        *(_from_endogenous(item, config) for item in endogenous.items),
    ]
    grouped: dict[str, list[StimulusPanelRecord]] = defaultdict(list)
    for record in raw_records:
        grouped[record.dedup_key].append(record)

    merged: list[StimulusPanelRecord] = []
    decisions: list[PanelAdmissionDecision] = []
    duplicate_count = 0
    for dedup_key in sorted(grouped):
        group = grouped[dedup_key]
        canonical = _merge_duplicate_group(group, config)
        merged.append(canonical)
        for duplicate in group:
            if duplicate.stimulus_id == canonical.stimulus_id:
                continue
            duplicate_count += 1
            decisions.append(
                PanelAdmissionDecision(
                    stimulus_id=duplicate.stimulus_id,
                    reason=PanelDecisionReason.DUPLICATE_COLLAPSED,
                    detail=f"collapsed into {canonical.stimulus_id}",
                    dedup_key=dedup_key,
                )
            )

    ordered = sorted(merged, key=lambda item: _panel_sort_key(item, config))
    accepted: list[StimulusPanelRecord] = []
    accepted_external = 0
    accepted_endogenous = 0
    unresolved_accepted = 0
    deferred_total = 0
    deferred_origin = 0
    deferred_unresolved = 0

    for record in ordered:
        if len(accepted) >= config.admission_policy.max_total_stimuli_per_cycle:
            deferred_total += 1
            decisions.append(_panel_decision(record, PanelDecisionReason.DEFERRED_TOTAL_BUDGET))
            continue
        is_external = record.origin_type is StimulusOrigin.EXTERNAL_PIT_CONTEXT
        if is_external:
            origin_budget_exhausted = (
                accepted_external
                >= config.admission_policy.max_external_stimuli_per_cycle
            )
        else:
            origin_budget_exhausted = (
                accepted_endogenous
                >= config.admission_policy.max_endogenous_stimuli_per_cycle
            )
        if origin_budget_exhausted:
            deferred_origin += 1
            decisions.append(_panel_decision(record, PanelDecisionReason.DEFERRED_ORIGIN_BUDGET))
            continue
        unresolved = record.selected_underlying_id is None
        if (
            unresolved
            and unresolved_accepted
            >= config.admission_policy.max_unresolved_stimuli_per_cycle
        ):
            deferred_unresolved += 1
            decisions.append(
                _panel_decision(
                    record, PanelDecisionReason.DEFERRED_UNRESOLVED_BUDGET
                )
            )
            continue

        accepted.append(record)
        if is_external:
            accepted_external += 1
        else:
            accepted_endogenous += 1
        unresolved_accepted += int(unresolved)
        decisions.append(_panel_decision(record, PanelDecisionReason.ACCEPTED))

    warnings: list[str] = []
    if duplicate_count:
        warnings.append(f"duplicate_records_collapsed:{duplicate_count}")
    if deferred_total:
        warnings.append(f"deferred_total_budget:{deferred_total}")
    if deferred_origin:
        warnings.append(f"deferred_origin_budget:{deferred_origin}")
    if deferred_unresolved:
        warnings.append(f"deferred_unresolved_budget:{deferred_unresolved}")
    if unresolved_accepted:
        warnings.append(f"unresolved_records_accepted:{unresolved_accepted}")

    input_count = len(external.items) + len(endogenous.items)
    if input_count == 0:
        status = ExecutionStatus.READY_EMPTY
    elif warnings:
        status = ExecutionStatus.DEGRADED
    else:
        status = ExecutionStatus.READY

    payload: dict[str, Any] = {
        "schema_version": "stimulus_panel.v2",
        "contract_version": "p3.s18.v1",
        "bus_id": config.bus_id,
        "dedup_key_version": config.dedup_key_version,
        "run_id": external.run_id,
        "cycle_id": external.cycle_id,
        "target_cycle_id": external.target_cycle_id,
        "as_of": external.as_of,
        "records": tuple(accepted),
        "admission_decisions": tuple(
            sorted(decisions, key=lambda item: (item.stimulus_id, item.reason.value, item.detail))
        ),
        "source_lineage_ids": (external.lineage_id, endogenous.lineage_id),
        "lineage_id": deterministic_id(
            "lineage:p3.s18.m02",
            external.lineage_id,
            endogenous.lineage_id,
            config.config_version,
        ),
        "status": status,
        "warnings": tuple(warnings),
        "metrics": EventBusMetrics(
            external_input_count=len(external.items),
            endogenous_input_count=len(endogenous.items),
            accepted_count=len(accepted),
            duplicate_collapsed_count=duplicate_count,
            deferred_total_budget_count=deferred_total,
            deferred_origin_budget_count=deferred_origin,
            deferred_unresolved_budget_count=deferred_unresolved,
            unresolved_accepted_count=unresolved_accepted,
            warning_count=len(warnings),
        ),
    }
    payload["content_hash"] = sha256_hex(payload)
    return StimulusPanel.model_validate(payload)


def _require_inputs(inputs: Mapping[str, Any]) -> None:
    missing = [name for name in REQUIRED_INPUTS if name not in inputs]
    unexpected = sorted(set(inputs) - set(REQUIRED_INPUTS))
    if missing or unexpected:
        raise S18InputError(f"missing={missing}; unexpected={unexpected}")


def _validate_streams(
    external: ResolvedExternalStimulusStreamInput,
    endogenous: EndogenousStimulusStream,
    config: StimulusBusConfig,
) -> None:
    if external.status in {ExecutionStatus.BLOCKED, ExecutionStatus.FAILED}:
        raise S18InputError(f"external stream status is {external.status}")
    if endogenous.status in {ExecutionStatus.BLOCKED, ExecutionStatus.FAILED}:
        raise S18InputError(f"endogenous stream status is {endogenous.status}")
    identity_pairs = {
        "run_id": (external.run_id, endogenous.run_id),
        "cycle_id": (external.cycle_id, endogenous.cycle_id),
        "target_cycle_id": (external.target_cycle_id, endogenous.target_cycle_id),
        "as_of": (external.as_of, endogenous.as_of),
    }
    mismatches = [name for name, pair in identity_pairs.items() if pair[0] != pair[1]]
    if mismatches:
        raise S18InputError(f"stream identity mismatch: {mismatches}")
    if config.allow_same_cycle_endogenous:
        raise S18InputError("S18 v1 forbids same-cycle endogenous stimuli")
    if config.verify_input_content_hashes:
        external_hash = hash_without_field(external)
        endogenous_hash = hash_without_field(endogenous)
        if external_hash != external.content_hash:
            raise S18HashMismatchError("resolved external stream content_hash mismatch")
        if endogenous_hash != endogenous.content_hash:
            raise S18HashMismatchError("endogenous stream content_hash mismatch")
    for item in external.items:
        if item.target_cycle_id != external.target_cycle_id:
            raise S18TemporalViolationError("external item target cycle mismatch")
        if item.available_at > external.as_of:
            raise S18TemporalViolationError("external item is future relative to as_of")
        if item.resolution_status is ResolutionStatus.INVALID:
            raise S18InputError("invalid external resolution cannot enter event bus")
        if item.proposition_status is PropositionStatus.INVALID:
            raise S18InputError("invalid proposition cannot enter event bus")
    for item in endogenous.items:
        if item.target_cycle_id != endogenous.target_cycle_id:
            raise S18TemporalViolationError("endogenous item target cycle mismatch")
        if item.available_at > endogenous.as_of:
            raise S18TemporalViolationError("endogenous item is future relative to as_of")


def _from_external(
    item: ResolvedExternalStimulusRecord,
    config: StimulusBusConfig,
) -> StimulusPanelRecord:
    priority = min(100, max(0, int(round(item.salience * 100))))
    dedup_key = _dedup_key(
        item.source_event_id,
        item.subject,
        item.available_at,
        item.content_hash,
        config,
    )
    return StimulusPanelRecord(
        stimulus_id=item.stimulus_id,
        origin_type=item.origin_type,
        origin_types=(item.origin_type,),
        merged_stimulus_ids=(item.stimulus_id,),
        source_event_id=item.source_event_id,
        causal_parent_ids=(item.causal_parent_id,) if item.causal_parent_id else (),
        created_cycle_ids=(item.created_cycle_id,),
        target_cycle_id=item.target_cycle_id,
        event_time=item.event_time,
        available_at=item.available_at,
        expires_at=None,
        subject=item.subject,
        stimulus_type=item.stimulus_type,
        intensity=item.intensity,
        salience=item.salience,
        priority=priority,
        resolution_status=item.resolution_status,
        underlying_candidates=item.underlying_candidates,
        selected_underlying_id=item.selected_underlying_id,
        proposition_id=item.proposition_id,
        horizon=item.horizon,
        proposition_status=item.proposition_status,
        content_hash=item.content_hash,
        evidence_refs=item.evidence_refs,
        lineage_ids=(item.lineage_id,),
        dedup_key=dedup_key,
        warnings=item.warnings,
    )


def _from_endogenous(
    item: EndogenousStimulusRecord,
    config: StimulusBusConfig,
) -> StimulusPanelRecord:
    dedup_key = _dedup_key(
        item.source_event_id,
        item.subject,
        item.available_at,
        item.content_hash,
        config,
    )
    return StimulusPanelRecord(
        stimulus_id=item.stimulus_id,
        origin_type=item.origin_type,
        origin_types=(item.origin_type,),
        merged_stimulus_ids=(item.stimulus_id,),
        source_event_id=item.source_event_id,
        causal_parent_ids=(item.causal_parent_id,),
        created_cycle_ids=(item.created_cycle_id,),
        target_cycle_id=item.target_cycle_id,
        event_time=item.event_time,
        available_at=item.available_at,
        expires_at=item.expires_at,
        subject=item.subject,
        stimulus_type=item.stimulus_type,
        intensity=item.intensity,
        salience=item.salience,
        priority=item.priority,
        resolution_status=item.resolution_status,
        underlying_candidates=item.underlying_candidates,
        selected_underlying_id=item.selected_underlying_id,
        proposition_id=item.proposition_id,
        horizon=item.horizon,
        proposition_status=item.proposition_status,
        content_hash=item.content_hash,
        evidence_refs=item.evidence_refs,
        lineage_ids=(item.lineage_id,),
        dedup_key=dedup_key,
        warnings=item.warnings,
    )


def _dedup_key(
    source_event_id: str,
    subject: str,
    available_at: datetime,
    content_hash: str,
    config: StimulusBusConfig,
) -> str:
    if config.dedup_key_version != "stimulus_dedup_v1":
        raise S18InputError(f"unsupported dedup key version: {config.dedup_key_version}")
    return sha256_hex(
        {
            "source_event_id": source_event_id,
            "subject": normalized_subject(subject),
            "available_at": available_at,
            "content_hash": content_hash,
        }
    )


def _merge_duplicate_group(
    group: list[StimulusPanelRecord],
    config: StimulusBusConfig,
) -> StimulusPanelRecord:
    if not group:
        raise S18InputError("cannot merge an empty duplicate group")
    economic_shapes = {
        (
            item.selected_underlying_id,
            item.proposition_id,
            item.horizon,
            item.resolution_status,
            item.proposition_status,
        )
        for item in group
    }
    if len(economic_shapes) != 1:
        raise S18DuplicateConflictError(
            f"dedup group {group[0].dedup_key} has conflicting economic resolution"
        )
    canonical = min(group, key=lambda item: _winner_key(item, config))
    origins = tuple(
        sorted(
            {origin for item in group for origin in item.origin_types},
            key=lambda origin: config.origin_precedence[origin],
        )
    )
    merged_ids = tuple(sorted({sid for item in group for sid in item.merged_stimulus_ids}))
    causal_ids = tuple(sorted({cid for item in group for cid in item.causal_parent_ids}))
    created_cycles = tuple(sorted({cid for item in group for cid in item.created_cycle_ids}))
    evidence_refs = tuple(sorted({ref for item in group for ref in item.evidence_refs}))
    lineage_ids = tuple(sorted({ref for item in group for ref in item.lineage_ids}))
    warnings = tuple(sorted({warning for item in group for warning in item.warnings}))
    expiries = [item.expires_at for item in group if item.expires_at is not None]
    return canonical.model_copy(
        update={
            "origin_types": origins,
            "merged_stimulus_ids": merged_ids,
            "causal_parent_ids": causal_ids,
            "created_cycle_ids": created_cycles,
            "event_time": min(item.event_time for item in group),
            "available_at": min(item.available_at for item in group),
            "expires_at": min(expiries) if expiries else None,
            "priority": max(item.priority for item in group),
            "salience": max(item.salience for item in group),
            "intensity": max(item.intensity for item in group),
            "evidence_refs": evidence_refs,
            "lineage_ids": lineage_ids,
            "warnings": warnings,
        }
    )


def _winner_key(
    item: StimulusPanelRecord,
    config: StimulusBusConfig,
) -> tuple[object, ...]:
    return (
        config.origin_precedence[item.origin_type],
        -item.priority,
        -item.salience,
        item.available_at,
        item.stimulus_id,
    )


def _panel_sort_key(
    item: StimulusPanelRecord,
    config: StimulusBusConfig,
) -> tuple[object, ...]:
    return (
        -item.priority,
        -item.salience,
        item.available_at,
        config.origin_precedence[item.origin_type],
        item.selected_underlying_id or "",
        item.proposition_id or "",
        item.stimulus_id,
    )


def _panel_decision(
    record: StimulusPanelRecord,
    reason: PanelDecisionReason,
) -> PanelAdmissionDecision:
    detail_by_reason = {
        PanelDecisionReason.ACCEPTED: "admitted to current-cycle stimulus panel",
        PanelDecisionReason.DEFERRED_TOTAL_BUDGET: "total cycle stimulus budget exhausted",
        PanelDecisionReason.DEFERRED_ORIGIN_BUDGET: "origin-specific stimulus budget exhausted",
        PanelDecisionReason.DEFERRED_UNRESOLVED_BUDGET: "unresolved stimulus budget exhausted",
        PanelDecisionReason.DUPLICATE_COLLAPSED: "duplicate collapsed",
    }
    return PanelAdmissionDecision(
        stimulus_id=record.stimulus_id,
        reason=reason,
        detail=detail_by_reason[reason],
        dedup_key=record.dedup_key,
    )



def merge_stimulus_event_bus_exactly_once(inputs: Mapping[str, Any], ledger) -> StimulusPanel:
    """Merge and persist an idempotency decision for every admitted stimulus."""
    panel = merge_stimulus_event_bus(inputs)
    for record in panel.records:
        result = ledger.admit(
            f"{panel.run_id}:{panel.cycle_id}:{record.stimulus_id}",
            record.model_dump(mode="json"),
        )
        if result.decision.value == "DUPLICATE_CONFLICT":
            raise S18DuplicateConflictError(f"persistent idempotency conflict for {record.stimulus_id}")
    return panel
