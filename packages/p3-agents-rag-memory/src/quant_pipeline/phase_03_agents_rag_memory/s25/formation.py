"""Implementation of P3.S25.M02 — relationship candidate evaluation."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime
from typing import Any, TypeAlias

from pydantic import ValidationError

from .artifacts import (
    ActiveRetroPolicyPatch,
    RelationshipCandidatePanel,
    RelationshipProposal,
    SocialToolAuditPanel,
    UpdatedSocialGraph,
)
from .common import (
    derived_id,
    lineage_id,
    log_event,
    require_effective_cycle,
    require_not_future,
    require_same_context,
)
from .errors import S25ContractError, S25PolicyError
from .types import (
    EligibilityStatus,
    EntitlementStatus,
    ExecutionStatus,
    RelationshipFormationConfig,
    RetroPatchStatus,
    ValidationStatus,
    reject_forbidden_policy_keys,
)

M02 = "P3.S25.M02"
AuditKey: TypeAlias = tuple[str, str, str]


def _validate(model: type[Any], value: Any, *, label: str) -> Any:
    try:
        return model.model_validate(value)
    except ValidationError as exc:
        raise S25ContractError(f"invalid {label}: {exc}") from exc


def _parse_inputs(
    updated_social_graph: Mapping[str, Any],
    social_tool_audit_panel: Mapping[str, Any],
    active_retro_policy_patch: Mapping[str, Any],
    relationship_formation_config: Mapping[str, Any],
) -> tuple[
    UpdatedSocialGraph,
    SocialToolAuditPanel,
    ActiveRetroPolicyPatch,
    RelationshipFormationConfig,
]:
    graph = _validate(UpdatedSocialGraph, updated_social_graph, label="updated_social_graph")
    audits = _validate(SocialToolAuditPanel, social_tool_audit_panel, label="social_tool_audit_panel")
    patch = _validate(ActiveRetroPolicyPatch, active_retro_policy_patch, label="active_retro_policy_patch")
    config = _validate(
        RelationshipFormationConfig,
        relationship_formation_config,
        label="relationship_formation_config",
    )
    require_same_context(graph, audits)
    return graph, audits, patch, config


def _effective_config(
    config: RelationshipFormationConfig,
    patch: ActiveRetroPolicyPatch,
    *,
    cycle_id: int,
    as_of: datetime,
) -> tuple[RelationshipFormationConfig, str]:
    if patch.status is RetroPatchStatus.NO_PATCH:
        return config, patch.patch_id
    require_not_future(patch.promoted_at, as_of=as_of, label="Retro patch")
    require_effective_cycle(patch.effective_cycle_id, current_cycle=cycle_id, label="Retro patch")
    if patch.change_type != "relationship_policy_update":
        return config, patch.patch_id
    if patch.change_target != "relationship_formation_config":
        raise S25PolicyError("relationship patch targets an unauthorized contract")
    reject_forbidden_policy_keys(patch.parameters)
    unknown = set(patch.parameters) - set(config.allowed_patch_parameters)
    if unknown:
        raise S25PolicyError(f"Retro patch contains unauthorized parameters: {sorted(unknown)}")
    data = config.model_dump(mode="python") | patch.parameters
    return RelationshipFormationConfig.model_validate(data), patch.patch_id


def _foundationudits(
    audits: SocialToolAuditPanel,
) -> dict[AuditKey, list[Any]]:
    grouped: dict[AuditKey, list[Any]] = defaultdict(list)
    for audit in audits.records:
        require_not_future(audit.occurred_at, as_of=audits.as_of_time, label="social tool audit")
        require_effective_cycle(
            audit.effective_cycle,
            current_cycle=audits.cycle_id,
            label="social tool audit",
        )
        grouped[(audit.source_person_id, audit.target_person_id, audit.relationship_type)].append(audit)
    return grouped


def _criteria(
    key: AuditKey,
    records: list[Any],
    people: set[str],
    existing: set[AuditKey],
    config: RelationshipFormationConfig,
) -> tuple[list[str], list[str], list[Any], EligibilityStatus]:
    source, target, relationship_type = key
    valid = [
        item
        for item in records
        if item.entitlement_status is EntitlementStatus.ENTITLED
        and item.execution_status is ExecutionStatus.SUCCEEDED
        and item.validation_status is ValidationStatus.VALIDATED
    ]
    count = len({item.event_id for item in valid})
    relevance = sum(item.mutual_relevance for item in valid) / count if count else 0.0
    checks = [
        ("persons_exist", "unknown_person", source in people and target in people, True),
        ("not_self_edge", "self_edge", source != target, True),
        (
            "relationship_type_allowed",
            "relationship_type_forbidden",
            relationship_type in config.allowed_relationship_types,
            True,
        ),
        ("edge_not_existing", "edge_already_exists", key not in existing, True),
        (
            "minimum_interactions",
            "insufficient_interactions",
            count >= config.minimum_repeated_interactions,
            False,
        ),
        (
            "minimum_mutual_relevance",
            "insufficient_mutual_relevance",
            relevance >= config.minimum_mutual_relevance,
            False,
        ),
        (
            "entitlement_and_execution_valid",
            "invalid_or_unentitled_interaction",
            not config.requires_social_tool_entitlement or len(valid) == len(records),
            True,
        ),
    ]
    passed = sorted(pass_name for pass_name, _, ok, _ in checks if ok)
    failed = sorted(fail_name for _, fail_name, ok, _ in checks if not ok)
    policy_failure = any(not ok and policy for _, _, ok, policy in checks)
    status = (
        EligibilityStatus.REJECTED_POLICY
        if policy_failure
        else EligibilityStatus.ELIGIBLE
        if not failed
        else EligibilityStatus.DEFERRED_INSUFFICIENT_EVIDENCE
    )
    return passed, failed, valid, status


def _proposal(
    key: AuditKey,
    records: list[Any],
    people: set[str],
    existing: set[AuditKey],
    config: RelationshipFormationConfig,
    *,
    run_id: str,
    cycle_id: int,
    as_of: datetime,
) -> RelationshipProposal:
    source, target, relationship_type = key
    passed, failed, valid, status = _criteria(key, records, people, existing, config)
    count = len({item.event_id for item in valid})
    relevance = sum(item.mutual_relevance for item in valid) / count if count else 0.0
    return RelationshipProposal(
        relationship_change_id=derived_id("relchg", run_id, cycle_id, *key),
        source_person_id=source,
        target_person_id=target,
        relationship_type=relationship_type,
        eligibility_status=status,
        criteria_passed=tuple(passed),
        criteria_failed=tuple(failed),
        supporting_event_ids=tuple(sorted(item.event_id for item in records)),
        interaction_count=count,
        mean_mutual_relevance=relevance,
        initial_trust_by_domain=config.initial_trust_by_domain,
        proposed_at=as_of,
        effective_cycle=cycle_id + 1,
        lineage_ids=tuple(sorted(item.lineage_id for item in records)),
    )


def _apply_source_caps(
    proposals: list[RelationshipProposal],
    config: RelationshipFormationConfig,
) -> tuple[RelationshipProposal, ...]:
    eligible: dict[str, list[RelationshipProposal]] = defaultdict(list)
    for item in proposals:
        if item.eligibility_status is EligibilityStatus.ELIGIBLE:
            eligible[item.source_person_id].append(item)
    capped: dict[str, RelationshipProposal] = {}
    for source_items in eligible.values():
        ordered = sorted(
            source_items,
            key=lambda item: (item.relationship_type, item.target_person_id, item.relationship_change_id),
        )
        for item in ordered[config.max_new_relationships_per_source_cycle :]:
            capped[item.relationship_change_id] = item.model_copy(
                update={
                    "eligibility_status": EligibilityStatus.DEFERRED_CAPACITY,
                    "criteria_failed": tuple(sorted((*item.criteria_failed, "source_capacity"))),
                }
            )
    return tuple(sorted((capped.get(x.relationship_change_id, x) for x in proposals), key=lambda x: x.relationship_change_id))


def evaluate_relationship_candidates(
    *,
    updated_social_graph: Mapping[str, Any],
    social_tool_audit_panel: Mapping[str, Any],
    active_retro_policy_patch: Mapping[str, Any],
    relationship_formation_config: Mapping[str, Any],
) -> RelationshipCandidatePanel:
    """Evaluate new-edge eligibility without mutating the graph."""
    graph, audits, patch, base_config = _parse_inputs(
        updated_social_graph,
        social_tool_audit_panel,
        active_retro_policy_patch,
        relationship_formation_config,
    )
    config, patch_id = _effective_config(
        base_config, patch, cycle_id=graph.cycle_id, as_of=graph.as_of_time
    )
    log_event("module_started", module_id=M02, run_id=graph.run_id, cycle_id=graph.cycle_id)
    people = {node.person_id for node in graph.nodes}
    existing = {(edge.source_person_id, edge.target_person_id, edge.relationship_type) for edge in graph.records}
    grouped = _foundationudits(audits)
    proposals = [
        _proposal(key, grouped[key], people, existing, config,
                  run_id=graph.run_id, cycle_id=graph.cycle_id, as_of=graph.as_of_time)
        for key in sorted(grouped)
    ]
    output = RelationshipCandidatePanel(
        schema_version="p3.s25.relationship_candidate_panel.v2",
        run_id=graph.run_id,
        cycle_id=graph.cycle_id,
        as_of_time=graph.as_of_time,
        lineage_id=lineage_id(M02, "relationship_candidate_panel", (
            graph.lineage_id, audits.lineage_id, patch.lineage_id
        )),
        records=_apply_source_caps(proposals, config),
        policy_version=config.version,
        policy_patch_id=patch_id,
    )
    log_event("module_succeeded", module_id=M02, run_id=graph.run_id, cycle_id=graph.cycle_id,
              status="IMPLEMENTED_QUALIFIED_INTERNAL", output_record_count=len(output.records),
              eligible_count=sum(x.eligibility_status is EligibilityStatus.ELIGIBLE for x in output.records))
    return output
