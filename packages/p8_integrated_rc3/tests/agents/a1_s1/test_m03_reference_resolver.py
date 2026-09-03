from __future__ import annotations

import json
from datetime import timedelta

import pytest

from quant_pipeline.phase_08_contracts.canonical import canonical_sha256, raw_sha256
from quant_pipeline.phase_08_contracts.common import ArtifactReference
from quant_pipeline.phase_08_contracts.enums import EvidenceResolutionStatus
from quant_pipeline.phase_08_contracts.p5 import P5BeliefEvidenceBundleV1
from quant_pipeline.phase_08_contracts.p6 import P6CandidateEconomicPackageV1
from quant_pipeline.phase_08_portfolio_control.s01_boundary.adapters import InMemoryArtifactStore
from quant_pipeline.phase_08_portfolio_control.s01_boundary.errors import (
    ExternalSystemError,
    HashMismatchError,
    LineageIntegrityError,
    TemporalIntegrityError,
)
from quant_pipeline.phase_08_portfolio_control.s01_boundary.modules.m01_phase7_handoff_contract_validator import (
    run_module as run_m01,
)
from quant_pipeline.phase_08_portfolio_control.s01_boundary.modules.m02_terminal_candidate_conservation_reconciler import (
    run_module as run_m02,
)
from quant_pipeline.phase_08_portfolio_control.s01_boundary.modules.m03_immutable_upstream_reference_resolver import (
    run_module as run_m03,
)
from quant_pipeline.phase_08_portfolio_control.s01_boundary.policies import (
    ContractCompatibilityPolicy,
    ReferenceResolutionPolicy,
)

from tests.agents.a1_s1.factories import P8_CUTOFF, P8_DECISION, full_fixture, raw_ref, rehash_p7_payload


def _m01_m02(fixture):
    m01 = run_m01(
        fixture.request.p7_handoff_bytes,
        context=fixture.request.context,
        policy=ContractCompatibilityPolicy(),
    )
    m02 = run_m02(m01.bundle, context=fixture.request.context)
    return m01, m02


def test_ranked_candidate_resolves_p6_p5_and_lineage() -> None:
    fixture = full_fixture(ranked=True)
    m01, m02 = _m01_m02(fixture)
    result = run_m03(
        m01.bundle,
        m02.ledger,
        store=fixture.artifact_store,
        context=fixture.request.context,
        policy=ReferenceResolutionPolicy(full_lineage_resolution=True),
    )
    candidate = result.evidence_index.candidates[0]
    assert candidate.status is EvidenceResolutionStatus.RESOLVED
    assert candidate.p6_package is not None
    assert candidate.p5_belief_bundle is not None
    assert all(receipt.status is EvidenceResolutionStatus.RESOLVED for receipt in candidate.reference_receipts)


def test_terminal_candidate_without_p6_reference_is_explicitly_unavailable() -> None:
    fixture = full_fixture(ranked=False)
    m01, m02 = _m01_m02(fixture)
    result = run_m03(
        m01.bundle,
        m02.ledger,
        store=fixture.artifact_store,
        context=fixture.request.context,
        policy=ReferenceResolutionPolicy(),
    )
    assert result.evidence_index.candidates[0].status is EvidenceResolutionStatus.UNAVAILABLE


def test_p6_raw_hash_mismatch_is_fatal() -> None:
    fixture = full_fixture(ranked=True)
    m01, m02 = _m01_m02(fixture)
    artifacts = fixture.artifact_store.export()
    assert fixture.p6_ref is not None
    artifacts[fixture.p6_ref.artifact_id] = b"tampered"
    with pytest.raises(HashMismatchError):
        run_m03(
            m01.bundle,
            m02.ledger,
            store=InMemoryArtifactStore(artifacts),
            context=fixture.request.context,
            policy=ReferenceResolutionPolicy(),
        )


def test_missing_referenced_artifact_is_fatal() -> None:
    fixture = full_fixture(ranked=True)
    m01, m02 = _m01_m02(fixture)
    artifacts = fixture.artifact_store.export()
    assert fixture.p6_ref is not None
    del artifacts[fixture.p6_ref.artifact_id]
    with pytest.raises(ExternalSystemError):
        run_m03(
            m01.bundle,
            m02.ledger,
            store=InMemoryArtifactStore(artifacts),
            context=fixture.request.context,
            policy=ReferenceResolutionPolicy(),
        )


def test_full_lineage_can_be_reserved_without_lookup() -> None:
    fixture = full_fixture(ranked=True)
    m01, m02 = _m01_m02(fixture)
    result = run_m03(
        m01.bundle,
        m02.ledger,
        store=fixture.artifact_store,
        context=fixture.request.context,
        policy=ReferenceResolutionPolicy(full_lineage_resolution=False),
    )
    statuses = {receipt.status for receipt in result.evidence_index.candidates[0].reference_receipts}
    assert statuses == {EvidenceResolutionStatus.RESERVED}


def test_p5_as_of_after_market_cutoff_is_rejected() -> None:
    fixture = full_fixture(ranked=True)
    assert fixture.p5_ref is not None and fixture.p6_ref is not None
    artifacts = fixture.artifact_store.export()
    p5 = P5BeliefEvidenceBundleV1.model_validate_json(artifacts[fixture.p5_ref.artifact_id], strict=True)
    modified = p5.model_copy(
        update={
            "as_of_time": P8_CUTOFF + timedelta(seconds=1),
            "decision_time": P8_CUTOFF + timedelta(seconds=2),
        }
    )
    modified_raw = modified.model_dump_json().encode()
    modified_ref = raw_ref(
        "p5-belief-future",
        "P5_BELIEF_EVIDENCE_REFERENCE_BUNDLE_V1",
        modified_raw,
        contract_version="P5_BELIEF_EVIDENCE_REFERENCE_BUNDLE_V1",
    )
    artifacts[modified_ref.artifact_id] = modified_raw
    p6 = P6CandidateEconomicPackageV1.model_validate_json(artifacts[fixture.p6_ref.artifact_id], strict=True)
    p6_modified = p6.model_copy(update={"p5_belief_bundle_ref": modified_ref})
    p6_raw = p6_modified.model_dump_json().encode()
    p6_ref = raw_ref(
        "p6-candidate-future-p5",
        "P6_CANDIDATE_ECONOMIC_PACKAGE_V1",
        p6_raw,
        contract_version="P6_CANDIDATE_ECONOMIC_PACKAGE_V1",
    )
    artifacts[p6_ref.artifact_id] = p6_raw
    handoff = json.loads(fixture.request.p7_handoff_bytes)
    handoff["ranked"][0]["p6_economic_package_ref"] = p6_ref.model_dump(mode="json")
    handoff["artifact_refs"] = [p6_ref.model_dump(mode="json")]
    raw_handoff = rehash_p7_payload(handoff)
    local_fixture = fixture
    m01 = run_m01(raw_handoff, context=local_fixture.request.context, policy=ContractCompatibilityPolicy())
    m02 = run_m02(m01.bundle, context=local_fixture.request.context)
    with pytest.raises(TemporalIntegrityError, match="as_of_time"):
        run_m03(
            m01.bundle,
            m02.ledger,
            store=InMemoryArtifactStore(artifacts),
            context=local_fixture.request.context,
            policy=ReferenceResolutionPolicy(),
        )


def test_candidate_identity_mismatch_is_rejected() -> None:
    fixture = full_fixture(ranked=True)
    assert fixture.p6_ref is not None
    artifacts = fixture.artifact_store.export()
    p6 = P6CandidateEconomicPackageV1.model_validate_json(artifacts[fixture.p6_ref.artifact_id], strict=True)
    altered = p6.model_copy(update={"candidate_id": "different"})
    raw = altered.model_dump_json().encode()
    new_ref = ArtifactReference(
        artifact_id="p6-different",
        artifact_type="P6_CANDIDATE_ECONOMIC_PACKAGE_V1",
        schema_version="1.0.0",
        contract_version="P6_CANDIDATE_ECONOMIC_PACKAGE_V1",
        content_sha256=raw_sha256(raw),
        available_at=fixture.p6_ref.available_at,
    )
    artifacts[new_ref.artifact_id] = raw
    handoff = json.loads(fixture.request.p7_handoff_bytes)
    handoff["ranked"][0]["p6_economic_package_ref"] = new_ref.model_dump(mode="json")
    handoff["artifact_refs"] = [new_ref.model_dump(mode="json")]
    raw_handoff = rehash_p7_payload(handoff)
    m01 = run_m01(raw_handoff, context=fixture.request.context, policy=ContractCompatibilityPolicy())
    m02 = run_m02(m01.bundle, context=fixture.request.context)
    with pytest.raises(LineageIntegrityError, match="candidate_id mismatch"):
        run_m03(
            m01.bundle,
            m02.ledger,
            store=InMemoryArtifactStore(artifacts),
            context=fixture.request.context,
            policy=ReferenceResolutionPolicy(),
        )
