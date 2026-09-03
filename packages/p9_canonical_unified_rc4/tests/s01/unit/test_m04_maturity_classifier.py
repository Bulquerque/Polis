from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from quant_pipeline.phase_09.contracts.integrity import IntegrityEnvelope, payload_sha256
from quant_pipeline.phase_09.contracts.maturity import (
    LifecycleStatus,
    MaturityBasis,
    MaturityState,
    MaturitySubject,
    MaturitySubjectManifest,
    MaturitySubjectManifestPayload,
    OutcomeMaturityPolicy,
    OutcomeMaturityPolicyRegistry,
)
from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.m04_maturity_classifier import (
    OutcomeMaturityAndCensoringClassifier,
)


def _manifest(subjects):
    payload = MaturitySubjectManifestPayload(manifest_id="m", subjects=tuple(subjects))
    return MaturitySubjectManifest(
        payload=payload,
        integrity=IntegrityEnvelope(payload_sha256=payload_sha256(payload)),
    )


def _subject(subject_id: str, t0, horizon, *, data_available=None, status=LifecycleStatus.OPEN, censor=None):
    return MaturitySubject(
        subject_id=subject_id,
        target_type="PRIMARY",
        instrument_id="i",
        contract_key="c",
        decision_time=t0,
        horizon_end=horizon,
        observation_end=horizon,
        data_available_at=data_available,
        lifecycle_status=status,
        censoring_reason=censor,
        reference_price=Decimal("100"),
        quantity=Decimal("1"),
        contract_multiplier=Decimal("1"),
    )


def test_mixed_horizons_classify_independently() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    evaluation = t0 + timedelta(days=3)
    subjects = (
        _subject("1d", t0, t0 + timedelta(days=1), data_available=t0 + timedelta(days=1)),
        _subject("5d", t0, t0 + timedelta(days=5), data_available=t0 + timedelta(days=5)),
    )
    policies = OutcomeMaturityPolicyRegistry(
        policies=(
            OutcomeMaturityPolicy(
                policy_id="p",
                metric_family="primary",
                target_type="PRIMARY",
                basis=MaturityBasis.HORIZON,
            ),
        )
    )
    panel, eligibility, _ = OutcomeMaturityAndCensoringClassifier().classify(
        manifest=_manifest(subjects),
        policy_registry=policies,
        evaluation_as_of=evaluation,
    )
    states = {decision.subject_id: decision.state for decision in panel.decisions}
    assert states == {"1d": MaturityState.MATURED, "5d": MaturityState.NOT_MATURED}
    assert "1d::primary" in eligibility.eligible_keys
    assert "5d::primary" in eligibility.ineligible_keys


def test_censored_subject_is_never_eligible() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    subject = _subject(
        "delisted",
        t0,
        t0 + timedelta(days=1),
        data_available=t0 + timedelta(days=1),
        status=LifecycleStatus.DELISTED,
        censor="DELISTED",
    )
    policies = OutcomeMaturityPolicyRegistry(
        policies=(
            OutcomeMaturityPolicy(
                policy_id="p",
                metric_family="primary",
                target_type="PRIMARY",
                basis=MaturityBasis.HORIZON,
            ),
        )
    )
    panel, _, _ = OutcomeMaturityAndCensoringClassifier().classify(
        manifest=_manifest((subject,)),
        policy_registry=policies,
        evaluation_as_of=t0 + timedelta(days=2),
    )
    assert panel.decisions[0].state is MaturityState.CENSORED
    assert not panel.decisions[0].eligible
