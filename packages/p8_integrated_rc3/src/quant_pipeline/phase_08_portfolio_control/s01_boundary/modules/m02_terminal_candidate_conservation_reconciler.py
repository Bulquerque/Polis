"""P8.S1.M02 — build the canonical candidate terminal-state ledger."""

from __future__ import annotations

from quant_pipeline.phase_08_contracts.canonical import canonical_sha256
from quant_pipeline.phase_08_contracts.enums import CandidateTerminalState, ReceiptStatus
from quant_pipeline.phase_08_contracts.s1 import (
    CandidateConservationProof,
    CandidateTerminalRecord,
    CandidateTerminalStateLedger,
    M02Result,
    ValidatedP7HandoffBundle,
)

from ..context import S1ExecutionContext
from ..errors import CandidateConservationError
from ..module_support import build_receipt

MODULE_ID = "P8.S1.M02"


def run_module(bundle: ValidatedP7HandoffBundle, *, context: S1ExecutionContext) -> M02Result:
    handoff = bundle.handoff
    records: list[CandidateTerminalRecord] = []
    for row in handoff.ranked:
        records.append(
            CandidateTerminalRecord(
                candidate_id=row.candidate_id,
                canonical_candidate_id=row.canonical_candidate_id,
                terminal_state=CandidateTerminalState.RANKED,
                comparison_group_id=row.comparison_group_id,
                rank=row.rank,
                p6_economic_package_ref=row.p6_economic_package_ref,
            )
        )
    terminal_sources = (
        (handoff.eligibility_blocked, CandidateTerminalState.ELIGIBILITY_BLOCKED),
        (handoff.safety_blocked, CandidateTerminalState.SAFETY_BLOCKED),
        (handoff.abstained, CandidateTerminalState.ABSTAINED),
    )
    for rows, state in terminal_sources:
        for row in rows:
            records.append(
                CandidateTerminalRecord(
                    candidate_id=row.candidate_id,
                    terminal_state=state,
                    reason_codes=row.reason_codes,
                    p6_economic_package_ref=row.p6_economic_package_ref,
                )
            )
    records.sort(key=lambda row: row.candidate_id)
    received = tuple(sorted(handoff.received_candidate_ids))
    terminal = tuple(row.candidate_id for row in records)
    equation_valid = received == terminal
    if not equation_valid:
        raise CandidateConservationError("normalized terminal ledger does not conserve received candidates")
    proof = CandidateConservationProof(
        received_count=len(received),
        ranked_count=sum(row.terminal_state is CandidateTerminalState.RANKED for row in records),
        eligibility_blocked_count=sum(
            row.terminal_state is CandidateTerminalState.ELIGIBILITY_BLOCKED for row in records
        ),
        safety_blocked_count=sum(row.terminal_state is CandidateTerminalState.SAFETY_BLOCKED for row in records),
        abstained_count=sum(row.terminal_state is CandidateTerminalState.ABSTAINED for row in records),
        received_ids_hash=canonical_sha256(received),
        terminal_ids_hash=canonical_sha256(terminal),
        equation_valid=True,
    )
    ledger = CandidateTerminalStateLedger(records=tuple(records), proof=proof)
    receipt = build_receipt(
        module_id=MODULE_ID,
        status=ReceiptStatus.SEMANTICALLY_CONSUMED,
        inputs=(bundle,),
        output=ledger,
        computed_at=context.computed_at,
    )
    return M02Result(ledger=ledger, receipt=receipt)
