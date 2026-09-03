
"""P8.S2.M05 — construct static-only action universe with complete candidate conservation."""

from __future__ import annotations

from quant_pipeline.phase_08_contracts.canonical import canonical_sha256
from quant_pipeline.phase_08_contracts.enums import CandidateTerminalState

from ..context import S2ExecutionContext
from ..contracts.enums import StaticActionState
from ..contracts.results import M05Result
from ..contracts.universe import (
    StaticActionDecision,
    StaticAdmissibleActionUniverse,
    StaticUniverseConservationProof,
)
from ..errors import StaticUniverseIntegrityError
from ..module_support import build_receipt, seal
from ..policies import StaticAdmissionPolicy

MODULE_ID = "P8.S2.M05"


def run_module(bundle, m01, m03, *, context: S2ExecutionContext, policy: StaticAdmissionPolicy) -> M05Result:
    normalized = {row.candidate_id: row for row in m01.normalized_intents.candidates}
    redundant_map: dict[str, str] = {}
    if policy.collapse_exact_redundancy:
        for group in m03.equivalence_groups.groups:
            if not group.hard_redundant_eligible:
                continue
            for member in group.members:
                if member.candidate_id != group.representative_candidate_id:
                    redundant_map[member.candidate_id] = group.representative_candidate_id
    decisions: list[StaticActionDecision] = []
    for record in sorted(bundle.terminal_ledger.records, key=lambda item: item.candidate_id):
        if record.terminal_state is not CandidateTerminalState.RANKED:
            decisions.append(StaticActionDecision(
                candidate_id=record.candidate_id,
                state=StaticActionState.P7_TERMINAL_PRESERVED,
                reason_codes=record.reason_codes,
            ))
            continue
        candidate = normalized.get(record.candidate_id)
        if candidate is None:
            decisions.append(StaticActionDecision(
                candidate_id=record.candidate_id,
                state=StaticActionState.REFERENCE_UNRESOLVED,
                reason_codes=("NORMALIZED_INTENT_MISSING",),
            ))
            continue
        if candidate.unit_economics.payoff_status not in policy.usable_payoff_statuses:
            decisions.append(StaticActionDecision(
                candidate_id=record.candidate_id,
                state=StaticActionState.STATIC_CAPABILITY_UNSUPPORTED,
                reason_codes=("PAYOFF_CAPABILITY_UNUSABLE",),
            ))
            continue
        if candidate.unit_economics.lifecycle_status not in policy.usable_lifecycle_statuses:
            decisions.append(StaticActionDecision(
                candidate_id=record.candidate_id,
                state=StaticActionState.STATIC_CAPABILITY_UNSUPPORTED,
                reason_codes=("LIFECYCLE_CAPABILITY_UNUSABLE",),
            ))
            continue
        representative = redundant_map.get(record.candidate_id)
        if representative is not None:
            decisions.append(StaticActionDecision(
                candidate_id=record.candidate_id,
                state=StaticActionState.EXACT_REDUNDANT,
                reason_codes=("HARD_REDUNDANCY_POLICY_APPLIED",),
                representative_candidate_id=representative,
            ))
            continue
        decisions.append(StaticActionDecision(
            candidate_id=record.candidate_id,
            state=StaticActionState.FORWARD_TO_RISK,
        ))
    input_ids = tuple(sorted(bundle.snapshot.received_candidate_ids))
    decision_ids = tuple(sorted(row.candidate_id for row in decisions))
    if input_ids != decision_ids:
        raise StaticUniverseIntegrityError("static action universe does not conserve S1 candidates")
    forwarded = tuple(sorted(row.candidate_id for row in decisions if row.state is StaticActionState.FORWARD_TO_RISK))
    terminal = sum(row.state is StaticActionState.P7_TERMINAL_PRESERVED for row in decisions)
    excluded = len(decisions) - len(forwarded) - terminal
    proof = StaticUniverseConservationProof(
        input_candidate_count=len(input_ids),
        decision_count=len(decision_ids),
        forwarded_count=len(forwarded),
        terminal_preserved_count=terminal,
        excluded_count=excluded,
        input_ids_hash=canonical_sha256(input_ids),
        decision_ids_hash=canonical_sha256(decision_ids),
        equation_valid=len(input_ids) == len(decision_ids) == len(forwarded) + terminal + excluded,
    )
    universe = seal(StaticAdmissibleActionUniverse(
        contract_version="P8_STATIC_ADMISSIBLE_ACTION_UNIVERSE_V1",
        schema_version="1.0.0",
        snapshot_id=bundle.snapshot.snapshot_id,
        forwarded_candidate_ids=forwarded,
        decisions=tuple(decisions),
        proof=proof,
        content_sha256="0" * 64,
    ))
    receipt = build_receipt(
        module_id=MODULE_ID,
        inputs=(bundle.terminal_ledger, m01.normalized_intents, m03.equivalence_groups),
        output=universe,
        computed_at=context.computed_at,
    )
    return M05Result(static_action_universe=universe, receipt=receipt)

run_m05 = run_module
