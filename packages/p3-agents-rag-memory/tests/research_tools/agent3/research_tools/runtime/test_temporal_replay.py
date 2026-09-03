from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.models import PitProof


def test_pit_proof_rejects_latest_evidence_after_decision_time():
    decision = datetime(2024, 1, 10, tzinfo=UTC)
    body = {
        "decision_time": decision,
        "latest_available_at": decision + timedelta(seconds=1),
        "records_rejected_future": 0,
        "input_hashes": (),
    }
    with pytest.raises(ValueError, match="latest_available_at exceeds decision_time"):
        PitProof(**body, proof_hash=content_hash(body))


def test_pit_proof_hash_is_stable_for_identical_payload():
    decision = datetime(2024, 1, 10, tzinfo=UTC)
    body = {"decision_time": decision, "latest_available_at": decision, "input_hashes": ()}
    first = PitProof(**body, proof_hash=content_hash(body))
    second = PitProof(**body, proof_hash=content_hash(body))
    assert first == second
    assert first.proof_hash == second.proof_hash
