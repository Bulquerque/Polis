from __future__ import annotations

from datetime import timedelta

from quant_pipeline.phase_09.contracts.cohort import (
    CommitmentMatchState,
    HoldoutAccessLedger,
    HoldoutAccessRecord,
    HoldoutPurpose,
)
from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.m01_handoff_validator import (
    P8EvaluationHandoffValidator,
)
from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.m02_lineage_resolver import (
    ImmutableLineageChainResolver,
)
from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.m04_maturity_classifier import (
    OutcomeMaturityAndCensoringClassifier,
)
from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.m05_outcome_assembler import (
    RealizedOutcomeAndMarkQualityAssembler,
)
from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.m06_cohort_commitment_matcher import (
    EvaluationCohortAndCommitmentMatcher,
)
from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.runner import S1Runner
from quant_pipeline.phase_09.contracts.maturity import MaturitySubjectManifest
from quant_pipeline.phase_09.contracts.outcomes import ExecutedOutcomePanel, MarketMarkPanel, MarkingPolicy


def _inputs(fixture):
    validator = P8EvaluationHandoffValidator(
        compatibility=fixture.compatibility,
        module_registry=fixture.module_registry,
        schema_registry=fixture.schema_registry,
        artifact_store=fixture.store,
    )
    validated = validator.validate(fixture.handoff).validated
    assert validated is not None
    graph = ImmutableLineageChainResolver(fixture.store).resolve(
        validated,
        fixture.lineage_policy,
    ).graph
    assert graph is not None
    runner = S1Runner(
        artifact_store=fixture.store,
        compatibility=fixture.compatibility,
        module_registry=fixture.module_registry,
        schema_registry=fixture.schema_registry,
        clock=fixture.clock,
    )
    subjects = runner._parse_role(validated, "maturity_subject_manifest", MaturitySubjectManifest)
    maturity, _, _ = OutcomeMaturityAndCensoringClassifier().classify(
        manifest=subjects,
        policy_registry=fixture.maturity_policies,
        evaluation_as_of=fixture.evaluation_as_of,
    )
    executed = runner._parse_role(validated, "executed_outcome_panel", ExecutedOutcomePanel)
    marks = runner._parse_role(validated, "market_mark_panel", MarketMarkPanel)
    policy = runner._parse_role(validated, "marking_policy_snapshot", MarkingPolicy)
    outcomes, _, _, _ = RealizedOutcomeAndMarkQualityAssembler().assemble(
        subjects=subjects,
        maturity_panel=maturity,
        executed_outcomes=executed.records,
        market_marks=marks.records,
        policy=policy,
        evaluation_as_of=fixture.evaluation_as_of,
    )
    return subjects, maturity, outcomes, graph


def test_cohort_freezes_with_precommitted_policy(full_fixture) -> None:
    subjects, maturity, outcomes, graph = _inputs(full_fixture)
    result = EvaluationCohortAndCommitmentMatcher().match(
        subjects=subjects,
        maturity_panel=maturity,
        outcomes=outcomes,
        lineage=graph,
        commitments=full_fixture.commitments,
        cohort_policies=full_fixture.cohort_policies,
        holdout_access=HoldoutAccessLedger(),
        evaluation_as_of=full_fixture.evaluation_as_of,
    )
    assert result.cohort is not None
    assert result.report.state is CommitmentMatchState.COHORT_FROZEN
    assert result.cohort.records[0].subject_id == "subject-1"


def test_unapproved_holdout_access_contaminates(full_fixture) -> None:
    subjects, maturity, outcomes, graph = _inputs(full_fixture)
    access = HoldoutAccessRecord(
        access_id="access-1",
        dataset_id="holdout-1",
        actor_id="researcher",
        accessed_at=full_fixture.evaluation_as_of - timedelta(hours=1),
        purpose=HoldoutPurpose.TUNING,
        approved=False,
    )
    result = EvaluationCohortAndCommitmentMatcher().match(
        subjects=subjects,
        maturity_panel=maturity,
        outcomes=outcomes,
        lineage=graph,
        commitments=full_fixture.commitments,
        cohort_policies=full_fixture.cohort_policies,
        holdout_access=HoldoutAccessLedger(records=(access,)),
        evaluation_as_of=full_fixture.evaluation_as_of,
    )
    assert result.report.state is CommitmentMatchState.HOLDOUT_CONTAMINATED
    assert result.holdout_report.contaminated


def test_missing_commitment_and_missing_policy_fail_closed(full_fixture) -> None:
    from quant_pipeline.phase_09.contracts.cohort import (
        CohortPolicyRegistry,
        ResearchCommitment,
        ResearchCommitmentRegistry,
    )
    from quant_pipeline.phase_09.contracts.integrity import payload_sha256

    subjects, maturity, outcomes, graph = _inputs(full_fixture)
    matcher = EvaluationCohortAndCommitmentMatcher()
    missing_commitment = matcher.match(
        subjects=subjects,
        maturity_panel=maturity,
        outcomes=outcomes,
        lineage=graph,
        commitments=ResearchCommitmentRegistry(commitments=()),
        cohort_policies=full_fixture.cohort_policies,
        holdout_access=HoldoutAccessLedger(),
        evaluation_as_of=full_fixture.evaluation_as_of,
    )
    assert missing_commitment.cohort is None
    assert missing_commitment.report.state is CommitmentMatchState.COMMITMENT_MISMATCH

    source = full_fixture.commitments.commitments[0]
    payload = {
        "commitment_id": "missing-policy-commitment",
        "created_at": source.created_at,
        "effective_from": source.effective_from,
        "metric_ids": source.metric_ids,
        "cohort_policy_id": "unknown-policy",
        "holdout_dataset_ids": source.holdout_dataset_ids,
    }
    commitment = ResearchCommitment(**payload, commitment_sha256=payload_sha256(payload))
    missing_policy = matcher.match(
        subjects=subjects,
        maturity_panel=maturity,
        outcomes=outcomes,
        lineage=graph,
        commitments=ResearchCommitmentRegistry(commitments=(commitment,)),
        cohort_policies=CohortPolicyRegistry(policies=()),
        holdout_access=HoldoutAccessLedger(),
        evaluation_as_of=full_fixture.evaluation_as_of,
    )
    assert missing_policy.cohort is None
    assert "P9_S1_COHORT_POLICY_MISSING" in missing_policy.report.reason_codes


def test_minimum_sample_gate_does_not_publish_cohort(full_fixture) -> None:
    from quant_pipeline.phase_09.contracts.cohort import CohortPolicy, CohortPolicyRegistry

    subjects, maturity, outcomes, graph = _inputs(full_fixture)
    source = full_fixture.cohort_policies.policies[0]
    strict_policy = CohortPolicy(
        policy_id=source.policy_id,
        allowed_target_types=source.allowed_target_types,
        allowed_evidence_classes=source.allowed_evidence_classes,
        minimum_sample=2,
        require_complete_lineage=True,
    )
    result = EvaluationCohortAndCommitmentMatcher().match(
        subjects=subjects,
        maturity_panel=maturity,
        outcomes=outcomes,
        lineage=graph,
        commitments=full_fixture.commitments,
        cohort_policies=CohortPolicyRegistry(policies=(strict_policy,)),
        holdout_access=HoldoutAccessLedger(),
        evaluation_as_of=full_fixture.evaluation_as_of,
    )
    assert result.cohort is None
    assert result.report.state is CommitmentMatchState.INSUFFICIENT_ELIGIBLE_SAMPLE
