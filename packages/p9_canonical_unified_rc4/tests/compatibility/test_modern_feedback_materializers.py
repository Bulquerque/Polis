from __future__ import annotations

from datetime import UTC, datetime

import pytest

from quant_pipeline.phase_09.compatibility.errors import ContractMismatchError
from quant_pipeline.phase_09.compatibility.modern_feedback import (
    P0FeedbackAuthorization,
    materialize_modern_p5_feedback,
    materialize_modern_p7_feedback,
)
from quant_pipeline.phase_09.subphases.s09_competition_promotion.enums import (
    EvidenceQuality,
    FeedbackEffectType,
    FeedbackPhase,
    FeedbackValidationState,
)
from quant_pipeline.phase_09.subphases.s09_competition_promotion.models.common import (
    ArtifactReference,
    CycleRef,
    EvidenceReference,
)
from quant_pipeline.phase_09.subphases.s09_competition_promotion.models.feedback import (
    CategoricalChangeBounds,
    FeedbackValidationDecision,
    NumericChangeBounds,
    P9P5ForecastFeedback,
    P9P7RankingFeedback,
    ValidatedNextCycleFeedbackManifest,
)

NOW = datetime(2026, 8, 4, 15, tzinfo=UTC)
SOURCE = CycleRef(cycle_id="cycle-1", ordinal=1)
TARGET = CycleRef(cycle_id="cycle-2", ordinal=2)


def _evidence() -> EvidenceReference:
    artifact = ArtifactReference(
        artifact_id="artifact-feedback-evidence",
        artifact_role="feedback_evidence",
        schema_name="FeedbackEvidence",
        schema_version="1.0.0",
        schema_sha256="1" * 64,
        payload_sha256="2" * 64,
        producer_module_id="P9.S9.M03",
        run_id="run-p9",
        cycle=SOURCE,
        available_at=NOW,
        location="memory://feedback-evidence",
    )
    return EvidenceReference(
        evidence_id="evidence-1",
        artifact_ref=artifact,
        quality=EvidenceQuality.FACTUAL_OBSERVED,
        summary="qualified prior-cycle evidence",
    )


def _manifest(package) -> ValidatedNextCycleFeedbackManifest:
    decision = FeedbackValidationDecision(
        feedback_id=package.feedback_id,
        state=FeedbackValidationState.VALIDATED_PENDING_P0,
        reason_codes=(),
        requires_p0_authorization=True,
    )
    return ValidatedNextCycleFeedbackManifest(
        accepted=(package,), rejected=(), reserved=(), decisions=(decision,)
    )


def _authorization(feedback_id: str) -> P0FeedbackAuthorization:
    return P0FeedbackAuthorization(
        authorization_id="p0-auth-1",
        authorized_feedback_ids=(feedback_id,),
        authorized_at=NOW,
        authorizer="P0",
    )


def test_p5_materializer_requires_p0_and_is_consumed_by_modern_p5():
    package = P9P5ForecastFeedback(
        feedback_id="feedback-p5-1",
        source_cycle=SOURCE,
        target_cycle=TARGET,
        target_policy_id="resolver-a",
        target_policy_version="1.0.0",
        feedback_type="resolver-bound-review",
        effect_type=FeedbackEffectType.POLICY_BOUND_CHANGE,
        evidence_refs=(_evidence(),),
        confidence=0.9,
        economic_materiality=1.0,
        numeric_change_bounds=(
            NumericChangeBounds(parameter_name="alpha", minimum=0.1, maximum=0.9),
        ),
        expires_after_cycle=CycleRef(cycle_id="cycle-3", ordinal=3),
        reason_codes=("P9_FEEDBACK_TEST",),
    )
    manifest = _manifest(package)
    with pytest.raises(ContractMismatchError):
        materialize_modern_p5_feedback(
            validated_manifest=manifest,
            source_run_id="run-p9",
            promotion_decision_id="promotion-1",
            created_at=NOW,
            available_at=NOW,
            checked_at=NOW,
        )
    result = materialize_modern_p5_feedback(
        validated_manifest=manifest,
        source_run_id="run-p9",
        promotion_decision_id="promotion-1",
        created_at=NOW,
        available_at=NOW,
        checked_at=NOW,
        authorization=_authorization(package.feedback_id),
    )
    from quant_pipeline.phase_05_underlying_forecasts.domain.feedback import PriorCycleFeedbackReport

    report = PriorCycleFeedbackReport.model_validate(result.report)
    assert report.records[0].effect_type.value == "HYPERPARAMETER_BOUNDS"
    assert report.records[0].effect_payload == {
        "parameter": "alpha", "minimum": 0.1, "maximum": 0.9,
    }


def test_p7_materializer_requires_p0_and_is_consumed_by_modern_p7():
    package = P9P7RankingFeedback(
        feedback_id="feedback-p7-1",
        source_cycle=SOURCE,
        target_cycle=TARGET,
        target_policy_id="ranker-a",
        target_policy_version="1.0.0",
        feedback_type="ranker-eligibility-review",
        effect_type=FeedbackEffectType.ELIGIBILITY_REVIEW,
        evidence_refs=(_evidence(),),
        confidence=0.9,
        economic_materiality=1.0,
        categorical_change_bounds=(
            CategoricalChangeBounds(parameter_name="ranker-a", allowed_values=("ELIGIBLE",)),
        ),
        expires_after_cycle=CycleRef(cycle_id="cycle-3", ordinal=3),
        reason_codes=("P9_FEEDBACK_TEST",),
    )
    manifest = _manifest(package)
    result = materialize_modern_p7_feedback(
        validated_manifest=manifest,
        source_run_id="run-p9",
        decision_time=NOW,
        created_at=NOW,
        checked_at=NOW,
        authorization=_authorization(package.feedback_id),
    )
    from quant_pipeline.phase_07_strategy_tournament.foundation.s1_boundary.feedback import execute

    outputs = execute(
        result.report,
        result.manifest,
        {
            "context": {
                "pipeline_version": "2.3.1rc4",
                "run_id": "run-p7-next",
                "cycle_id": "cycle-2",
                "decision_time": NOW.isoformat(),
                "available_at": NOW.isoformat(),
                "created_at": NOW.isoformat(),
                "lineage_id": "lineage-p7-next",
            },
            "policy": {"allowed_scope": {"target_policy_id": "ranker-a"}},
        },
    )
    records = outputs["ranking_feedback_context"]["records"]
    assert records[0]["adjustments"][0]["adjustment_type"] == "MODEL_ELIGIBILITY"
