from __future__ import annotations

import json

from quant_pipeline.phase_08_contracts.canonical import canonical_sha256
from quant_pipeline.phase_08_contracts.enums import CandidateTerminalState
from quant_pipeline.phase_08_portfolio_control.s01_boundary.modules.m01_phase7_handoff_contract_validator import (
    run_module as run_m01,
)
from quant_pipeline.phase_08_portfolio_control.s01_boundary.modules.m02_terminal_candidate_conservation_reconciler import (
    run_module as run_m02,
)
from quant_pipeline.phase_08_portfolio_control.s01_boundary.policies import ContractCompatibilityPolicy

from tests.agents.a1_s1.factories import full_fixture, rehash_p7_payload


def _ledger(raw: bytes):
    fixture = full_fixture(ranked=True)
    m01 = run_m01(raw, context=fixture.request.context, policy=ContractCompatibilityPolicy())
    return run_m02(m01.bundle, context=fixture.request.context).ledger


def test_ranked_candidate_is_normalized_into_terminal_ledger() -> None:
    fixture = full_fixture(ranked=True)
    ledger = _ledger(fixture.request.p7_handoff_bytes)
    assert ledger.records[0].terminal_state is CandidateTerminalState.RANKED
    assert ledger.proof.equation_valid is True
    assert ledger.proof.ranked_count == 1


def test_all_abstained_is_conserved() -> None:
    fixture = full_fixture(ranked=False)
    m01 = run_m01(
        fixture.request.p7_handoff_bytes,
        context=fixture.request.context,
        policy=ContractCompatibilityPolicy(),
    )
    ledger = run_m02(m01.bundle, context=fixture.request.context).ledger
    assert ledger.proof.abstained_count == 1
    assert ledger.records[0].reason_codes == ("CONFIDENCE_UNAVAILABLE",)


def test_permutation_of_input_rows_does_not_change_ledger_hash() -> None:
    fixture = full_fixture(ranked=False)
    first = _ledger(fixture.request.p7_handoff_bytes)
    payload = json.loads(fixture.request.p7_handoff_bytes)
    payload["received_candidate_ids"] = list(reversed(payload["received_candidate_ids"]))
    second = _ledger(rehash_p7_payload(payload))
    assert canonical_sha256(first) == canonical_sha256(second)
