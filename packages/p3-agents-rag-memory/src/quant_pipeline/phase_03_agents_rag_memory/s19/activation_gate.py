from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN
from math import ceil

from .errors import S19HashMismatchError, S19PopulationMismatchError, S19TemporalError
from .hashing import deterministic_id, deterministic_seed, hash_without_field, sha256_hex
from .models import (
    ActivationComponents,
    ActivationConfig,
    ActivationDecision,
    ActivationDecisionReason,
    ActivationMetrics,
    ActivationPanel,
    ActivationReason,
    ActivationRecord,
    CurrentPersonStatePanelInput,
    ExecutionStatus,
    PersonActivationProfile,
    PersonSeedRecord,
    PersonSeedPanelInput,
    PersonStateRecord,
    ResolutionStatus,
    StimulusPanelInput,
    StimulusPanelRecord,
    TriggerType,
)


def _score_product(*values: float) -> float:
    result = Decimal("1")
    for value in values:
        result *= Decimal(str(value))
    return float(result.quantize(Decimal("0.000000000001"), rounding=ROUND_HALF_EVEN))


def _relevance(profile: PersonActivationProfile, stimulus: StimulusPanelRecord) -> float:
    scores: list[float] = []
    if stimulus.selected_underlying_id is not None:
        scores.extend(
            item.score
            for item in profile.underlying_relevance
            if item.key == stimulus.selected_underlying_id
        )
    if stimulus.proposition_id is not None:
        scores.extend(
            item.score
            for item in profile.proposition_relevance
            if item.key == stimulus.proposition_id
        )
    if stimulus.horizon is not None:
        scores.extend(
            item.score
            for item in profile.horizon_relevance
            if item.key == stimulus.horizon
        )
    return max(scores) if scores else profile.default_relevance


def _sensitivity(profile: PersonActivationProfile, stimulus: StimulusPanelRecord) -> float:
    scores = [
        item.score
        for item in profile.stimulus_type_sensitivity
        if item.stimulus_type == stimulus.stimulus_type
    ]
    return max(scores) if scores else profile.default_tag_sensitivity


def _attention(state: PersonStateRecord, stimulus: StimulusPanelRecord) -> float:
    scores: list[float] = []
    if stimulus.selected_underlying_id is not None:
        scores.extend(
            item.score
            for item in state.underlying_attention
            if item.key == stimulus.selected_underlying_id
        )
    if stimulus.proposition_id is not None:
        scores.extend(
            item.score
            for item in state.proposition_attention
            if item.key == stimulus.proposition_id
        )
    return max(scores) if scores else state.current_attention


def _exposure(profile: PersonActivationProfile, stimulus: StimulusPanelRecord) -> float:
    scores = [
        item.score
        for item in profile.origin_exposure
        if item.origin_type == stimulus.origin_type
    ]
    return max(scores) if scores else profile.default_exposure


def _candidate_sort_key(candidate: ActivationRecord) -> tuple:
    return (
        -candidate.activation_score,
        -candidate.stimulus_priority,
        candidate.stimulus_available_at,
        candidate.tie_break_hash,
        candidate.person_id,
        candidate.stimulus_id,
    )


def _verify_hashes(
    stimulus_panel: StimulusPanelInput,
    state_panel: CurrentPersonStatePanelInput,
    seed_panel: PersonSeedPanelInput,
    config: ActivationConfig,
) -> None:
    if not config.verify_input_content_hashes:
        return
    for name, value in [
        ("stimulus_panel", stimulus_panel),
        ("current_person_state_panel", state_panel),
        ("person_seed_panel", seed_panel),
    ]:
        if hash_without_field(value) != value.content_hash:
            raise S19HashMismatchError(f"{name} content_hash mismatch")


def _validate_population_alignment(
    stimulus_panel: StimulusPanelInput,
    state_panel: CurrentPersonStatePanelInput,
    seed_panel: PersonSeedPanelInput,
) -> None:
    if stimulus_panel.as_of != state_panel.as_of:
        raise S19TemporalError("stimulus and state panels must share the same as_of")
    if seed_panel.population_id != state_panel.population_id:
        raise S19PopulationMismatchError("state and seed population_id values differ")
    state_ids = {item.person_id for item in state_panel.records}
    seed_ids = {item.person_id for item in seed_panel.records}
    if state_ids != seed_ids:
        raise S19PopulationMismatchError("state and seed person sets differ")



@dataclass(slots=True)
class _ActivationCounters:
    inactive: int = 0
    no_exposure: int = 0
    unresolved_skipped: int = 0
    below_threshold: int = 0
    deferred_person: int = 0
    deferred_global: int = 0


def _candidate_for(
    *,
    person: PersonSeedRecord,
    state: PersonStateRecord,
    stimulus: StimulusPanelRecord,
    panel: StimulusPanelInput,
    seed_panel: PersonSeedPanelInput,
    config: ActivationConfig,
    counters: _ActivationCounters,
) -> tuple[ActivationRecord | None, ActivationDecision | None]:
    activation_id = deterministic_id(
        "activation",
        panel.run_id,
        panel.cycle_id,
        person.person_id,
        stimulus.stimulus_id,
        config.formula_id,
    )
    tie_hash = sha256_hex([person.person_seed, panel.cycle_id, activation_id])
    relevance = _relevance(person.activation_profile, stimulus)
    sensitivity = _sensitivity(person.activation_profile, stimulus)
    attention = _attention(state, stimulus)
    exposure = _exposure(person.activation_profile, stimulus)
    score = _score_product(
        stimulus.intensity,
        relevance,
        sensitivity,
        attention,
        exposure,
    )
    threshold = person.activation_profile.activation_threshold
    reason: ActivationDecisionReason | None = None
    detail = ""
    if not state.is_active:
        reason = ActivationDecisionReason.INACTIVE_PERSON
        detail = "person state is inactive"
        counters.inactive += 1
    elif exposure <= 0.0:
        reason = ActivationDecisionReason.NO_EXPOSURE
        detail = "person has no exposure to stimulus origin"
        counters.no_exposure += 1
    elif (
        stimulus.resolution_status
        in {ResolutionStatus.UNRESOLVED, ResolutionStatus.AMBIGUOUS}
        and config.unresolved_stimulus_policy == "SKIP_WITH_AUDIT"
    ):
        reason = ActivationDecisionReason.UNRESOLVED_NOT_ALLOWED
        detail = "unresolved stimulus policy blocks candidate"
        counters.unresolved_skipped += 1
    elif score < threshold:
        reason = ActivationDecisionReason.BELOW_THRESHOLD
        detail = "activation score is below person-specific threshold"
        counters.below_threshold += 1

    if reason is not None:
        return None, ActivationDecision(
            person_id=person.person_id,
            stimulus_id=stimulus.stimulus_id,
            activation_id=activation_id,
            reason=reason,
            detail=detail,
            activation_score=score,
            threshold=threshold,
            tie_break_hash=tie_hash,
        )

    return ActivationRecord(
        activation_id=activation_id,
        person_id=person.person_id,
        stimulus_id=stimulus.stimulus_id,
        trigger_type=TriggerType.STIMULUS,
        activation_reason=ActivationReason.STIMULUS_THRESHOLD_MET,
        activation_score=score,
        threshold=threshold,
        components=ActivationComponents(
            stimulus_intensity=stimulus.intensity,
            relevance=relevance,
            tag_sensitivity=sensitivity,
            current_attention=attention,
            exposure=exposure,
        ),
        stimulus_priority=stimulus.priority,
        stimulus_available_at=stimulus.available_at,
        underlying_id=stimulus.selected_underlying_id,
        proposition_id=stimulus.proposition_id,
        horizon=stimulus.horizon,
        seed=deterministic_seed(person.person_seed, panel.cycle_id, activation_id),
        tie_break_hash=tie_hash,
        source_lineage_ids=tuple(sorted({seed_panel.lineage_id, *stimulus.lineage_ids})),
    ), None


def _collect_candidates(
    panel: StimulusPanelInput,
    state_panel: CurrentPersonStatePanelInput,
    seed_panel: PersonSeedPanelInput,
    config: ActivationConfig,
    counters: _ActivationCounters,
) -> tuple[dict[str, list[ActivationRecord]], list[ActivationDecision]]:
    state_by_person = {item.person_id: item for item in state_panel.records}
    candidates: dict[str, list[ActivationRecord]] = defaultdict(list)
    decisions: list[ActivationDecision] = []
    for person in sorted(seed_panel.records, key=lambda item: item.person_id):
        state = state_by_person[person.person_id]
        for stimulus in panel.records:
            candidate, decision = _candidate_for(
                person=person,
                state=state,
                stimulus=stimulus,
                panel=panel,
                seed_panel=seed_panel,
                config=config,
                counters=counters,
            )
            if decision is not None:
                decisions.append(decision)
            elif candidate is not None:
                candidates[person.person_id].append(candidate)
    return candidates, decisions


def _deferred_decision(
    candidate: ActivationRecord,
    reason: ActivationDecisionReason,
    detail: str,
) -> ActivationDecision:
    return ActivationDecision(
        person_id=candidate.person_id,
        stimulus_id=candidate.stimulus_id,
        activation_id=candidate.activation_id,
        reason=reason,
        detail=detail,
        activation_score=candidate.activation_score,
        threshold=candidate.threshold,
        tie_break_hash=candidate.tie_break_hash,
    )


def _apply_activation_caps(
    candidates_by_person: dict[str, list[ActivationRecord]],
    state_panel: CurrentPersonStatePanelInput,
    config: ActivationConfig,
    counters: _ActivationCounters,
) -> tuple[list[ActivationRecord], list[ActivationDecision], int]:
    provisional: list[ActivationRecord] = []
    decisions: list[ActivationDecision] = []
    for person_id in sorted(candidates_by_person):
        ordered = sorted(candidates_by_person[person_id], key=_candidate_sort_key)
        cap = config.max_extra_activations_per_person_per_cycle
        provisional.extend(ordered[:cap])
        for candidate in ordered[cap:]:
            counters.deferred_person += 1
            decisions.append(
                _deferred_decision(
                    candidate,
                    ActivationDecisionReason.DEFERRED_PERSON_CAP,
                    "candidate exceeded per-person cycle cap",
                )
            )

    active_population = sum(1 for state in state_panel.records if state.is_active)
    calculated_cap = ceil(active_population * config.global_cap.population_fraction)
    global_cap = min(
        config.global_cap.absolute_cap,
        max(config.global_cap.minimum_if_candidates, calculated_cap),
    )
    ordered = sorted(provisional, key=_candidate_sort_key)
    accepted = ordered[:global_cap]
    for candidate in ordered[global_cap:]:
        counters.deferred_global += 1
        decisions.append(
            _deferred_decision(
                candidate,
                ActivationDecisionReason.DEFERRED_GLOBAL_CAP,
                "candidate exceeded global cycle cap",
            )
        )
    decisions.extend(
        _deferred_decision(
            candidate,
            ActivationDecisionReason.ACCEPTED,
            "candidate passed threshold and activation caps",
        )
        for candidate in accepted
    )
    return sorted(accepted, key=_candidate_sort_key), decisions, global_cap if provisional else 0


def _activation_status(
    accepted: list[ActivationRecord],
    panel: StimulusPanelInput,
) -> tuple[ExecutionStatus, tuple[str, ...]]:
    stimulus_by_id = {record.stimulus_id: record for record in panel.records}
    unresolved = any(
        stimulus_by_id[item.stimulus_id].resolution_status
        in {ResolutionStatus.UNRESOLVED, ResolutionStatus.AMBIGUOUS}
        for item in accepted
    )
    warnings = ("unresolved_stimulus_accepted",) if unresolved else ()
    if not accepted:
        return ExecutionStatus.READY_EMPTY, warnings
    return (ExecutionStatus.DEGRADED if warnings else ExecutionStatus.READY), warnings


def build_activation_panel(
    stimulus_panel: StimulusPanelInput,
    state_panel: CurrentPersonStatePanelInput,
    seed_panel: PersonSeedPanelInput,
    config: ActivationConfig,
) -> ActivationPanel:
    """Calculate deterministic activations using explicit eligibility and cap stages."""

    _verify_hashes(stimulus_panel, state_panel, seed_panel, config)
    _validate_population_alignment(stimulus_panel, state_panel, seed_panel)
    counters = _ActivationCounters()
    candidates, decisions = _collect_candidates(
        stimulus_panel,
        state_panel,
        seed_panel,
        config,
        counters,
    )
    accepted, cap_decisions, global_cap = _apply_activation_caps(
        candidates,
        state_panel,
        config,
        counters,
    )
    decisions.extend(cap_decisions)
    decisions.sort(key=lambda item: (item.person_id, item.stimulus_id, item.reason.value))
    status, warnings = _activation_status(accepted, stimulus_panel)
    active_population = sum(1 for state in state_panel.records if state.is_active)

    payload = {
        "schema_version": "activation_panel.v2",
        "contract_version": "p3.s19.v1",
        "formula_id": config.formula_id,
        "run_id": stimulus_panel.run_id,
        "cycle_id": stimulus_panel.cycle_id,
        "target_cycle_id": stimulus_panel.target_cycle_id,
        "population_id": seed_panel.population_id,
        "as_of": stimulus_panel.as_of,
        "records": tuple(accepted),
        "decisions": tuple(decisions),
        "source_lineage_ids": tuple(
            sorted(
                {
                    stimulus_panel.lineage_id,
                    state_panel.lineage_id,
                    seed_panel.lineage_id,
                }
            )
        ),
        "lineage_id": deterministic_id(
            "lineage:p3.s19.m01",
            stimulus_panel.lineage_id,
            state_panel.lineage_id,
            seed_panel.lineage_id,
            config.config_version,
        ),
        "status": status,
        "warnings": warnings,
        "metrics": ActivationMetrics(
            stimulus_count=len(stimulus_panel.records),
            active_person_count=active_population,
            candidate_count=len(stimulus_panel.records) * len(seed_panel.records),
            accepted_count=len(accepted),
            below_threshold_count=counters.below_threshold,
            deferred_person_cap_count=counters.deferred_person,
            deferred_global_cap_count=counters.deferred_global,
            inactive_person_count=counters.inactive,
            no_exposure_count=counters.no_exposure,
            unresolved_skipped_count=counters.unresolved_skipped,
            global_cap_applied=global_cap,
            warning_count=len(warnings),
        ),
    }
    payload["content_hash"] = sha256_hex(payload)
    return ActivationPanel.model_validate(payload)
