from __future__ import annotations

import json
import os
import sys
from decimal import Decimal
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

P9_ROOT = Path(__file__).resolve().parents[2]
COMPONENTS_ROOT = P9_ROOT.parent
P5_ROOT = Path(os.environ.get('P5_COMPONENT_ROOT', COMPONENTS_ROOT / 'P5_CANONICAL_RC4'))
P6_ROOT = Path(os.environ.get('P6_COMPONENT_ROOT', COMPONENTS_ROOT / 'P6_CANONICAL_RC4'))
P7_ROOT = Path(os.environ.get('P7_COMPONENT_ROOT', COMPONENTS_ROOT / 'P7_CANONICAL_RC3'))
P8_ROOT = Path(os.environ.get('P8_COMPONENT_ROOT', COMPONENTS_ROOT / 'P8_INTEGRATED_RC3'))


def _baseline_root() -> Path:
    configured = os.environ.get('P0_P9_REFERENCE_ROOT')
    candidates = [Path(configured)] if configured else [P9_ROOT.parents[2]]
    for root in candidates:
        if root.exists() and all(
            (root / relative).exists()
            for relative in (
                'phase_00_zero_trust',
                'phase_01_ingestion',
                'phase_02_extracted',
                'phase_03_extracted',
                'phase_04_extracted',
            )
        ):
            return root
    pytest.skip('external P0-P7 reference tree not configured; set P0_P9_REFERENCE_ROOT')


def _p3_root() -> Path:
    return _baseline_root() / 'phase_03_extracted/phase_03_agents_rag_memory_agent_package_RC4_1'


P3_ROOT = _p3_root


for source in (P8_ROOT / 'src',):
    if source.exists() and str(source) not in sys.path:
        sys.path.insert(0, str(source))

from quant_pipeline.phase_09.compatibility.errors import ContractMismatchError, EvidenceIncompleteError
from quant_pipeline.phase_09.compatibility.legacy_feedback import (
    PortfolioFeedbackReport,
    RankingFeedbackReport,
    SignalFeedbackReport,
)
from quant_pipeline.phase_09.compatibility.models import (
    CompatibilityState,
    LegacyFeedbackHeader,
    P8NativePublicationRequest,
    SupplementalArtifact,
)
from quant_pipeline.phase_09.compatibility.p0_reporting import build_p0_control_plane_reports
from quant_pipeline.phase_09.compatibility.p0_consumer import validate_p0_control_plane_consumer
from quant_pipeline.phase_09.compatibility.p3_boundary import (
    build_p3_belief_feedback,
    build_p3_retro_context_package,
    validate_p3_belief_feedback_consumer,
    validate_p3_evaluation_boundary,
    validate_p3_retro_context_consumer,
)
from quant_pipeline.phase_09.compatibility.p8_feedback import materialize_p8_promoted_feedback
from quant_pipeline.phase_09.compatibility.fingerprints import verify_phase_package_fingerprint
from quant_pipeline.phase_09.compatibility.p8_ingress import publish_p8_native_handoff
from quant_pipeline.phase_09.contracts.handoff import P8HandoffMode
from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.m01_handoff_validator import (
    P8EvaluationHandoffValidator,
)
from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.ports import InMemoryArtifactStore


def _p8_models():
    from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.models_handoff import P9EvaluationHandoff
    from quant_pipeline.phase_08_portfolio_control.subphases.s10_audit_release.models_state import StatefulEvidenceBundle
    return P9EvaluationHandoff, StatefulEvidenceBundle


def _load_p8_pair():
    P9EvaluationHandoff, StatefulEvidenceBundle = _p8_models()
    state_path = P8_ROOT / 'tests/agents/subphases/s10/fixtures/input/stateful_evidence_bundle.json'
    result_path = P8_ROOT / 'tests/agents/subphases/s10/fixtures/expected/normal_result.json'
    state = StatefulEvidenceBundle.model_validate_json(state_path.read_text(), strict=False)
    result = json.loads(result_path.read_text())
    handoff = P9EvaluationHandoff.model_validate(result['p9_handoff'], strict=False)
    return handoff, state


def test_current_p8_native_publication_is_accepted_limited():
    handoff, state = _load_p8_pair()
    store = InMemoryArtifactStore()
    publication = publish_p8_native_handoff(
        p8_handoff=handoff,
        stateful_evidence_bundle=state,
        request=P8NativePublicationRequest(
            backtest_id='backtest-p8-native',
            producer_package_version='0.3.0rc3',
            published_at=datetime(2026, 8, 3, 17, tzinfo=UTC),
        ),
        artifact_store=store,
    )
    assert publication.mode is P8HandoffMode.P8_NATIVE_0_3_LIMITED
    assert 'nav_panel' in publication.missing_full_roles
    validator = P8EvaluationHandoffValidator(
        compatibility=publication.compatibility_matrix,
        module_registry=publication.module_registry,
        schema_registry=publication.schema_registry,
        artifact_store=store,
    )
    outcome = validator.validate(publication.handoff)
    assert outcome.validated is not None
    assert outcome.report.status.value == 'ACCEPTED_LIMITED'
    assert len(outcome.validated.accepted_artifacts) == 20


def test_current_p8_can_publish_full_only_with_explicit_supplements():
    handoff, state = _load_p8_pair()
    at = datetime(2026, 8, 3, 17, tzinfo=UTC)
    missing_roles = (
        'portfolio_decision_panel',
        'optimizer_decision_trace',
        'nav_panel',
        'exposure_panel',
        'drawdown_panel',
        'marking_policy_snapshot',
    )
    supplements = tuple(
        SupplementalArtifact(
            role=role,
            payload={'role': role, 'source': 'qualified-explicit-supplement'},
            schema_name=f'p8.supplement.{role}',
            schema_document={
                '$schema': 'https://json-schema.org/draft/2020-12/schema',
                'title': f'p8.supplement.{role}',
                'type': 'object',
                'additionalProperties': True,
            },
            producer_module_id='P8.S5.M07' if 'optimizer' in role or 'portfolio' in role else 'P8.S8.M05',
            record_count=1,
            grain=('record',),
            event_time=datetime(2026, 8, 3, 16, tzinfo=UTC),
        )
        for role in missing_roles
    )
    store = InMemoryArtifactStore()
    publication = publish_p8_native_handoff(
        p8_handoff=handoff,
        stateful_evidence_bundle=state,
        request=P8NativePublicationRequest(
            backtest_id='backtest-p8-full',
            producer_package_version='0.3.0rc3',
            published_at=at,
            require_full=True,
        ),
        artifact_store=store,
        supplemental_artifacts=supplements,
    )
    assert publication.mode is P8HandoffMode.FULL_V1
    assert publication.missing_full_roles == ()
    assert len(publication.handoff.payload.artifacts) == 26
    binding = next(
        item for item in publication.module_registry.modules if item.module_id == 'P8.S5.M07'
    )
    assert binding.subphase_id == 'P8.S5'
    validator = P8EvaluationHandoffValidator(
        compatibility=publication.compatibility_matrix,
        module_registry=publication.module_registry,
        schema_registry=publication.schema_registry,
        artifact_store=store,
    )
    outcome = validator.validate(publication.handoff)
    assert outcome.report.status.value == 'ACCEPTED_FULL'


def test_current_p8_cannot_be_mislabeled_full_without_supplements():
    handoff, state = _load_p8_pair()
    with pytest.raises(EvidenceIncompleteError):
        publish_p8_native_handoff(
            p8_handoff=handoff,
            stateful_evidence_bundle=state,
            request=P8NativePublicationRequest(
                backtest_id='backtest-p8-native',
                producer_package_version='0.3.0rc3',
                published_at=datetime(2026, 8, 3, 17, tzinfo=UTC),
                require_full=True,
            ),
            artifact_store=InMemoryArtifactStore(),
        )


def test_p8_candidate_context_mismatch_is_rejected():
    handoff, state = _load_p8_pair()
    changed = state.model_copy(update={'expected_candidate_ids': ('c1',)})
    with pytest.raises(ContractMismatchError):
        publish_p8_native_handoff(
            p8_handoff=handoff,
            stateful_evidence_bundle=changed,
            request=P8NativePublicationRequest(
                backtest_id='backtest-p8-native',
                producer_package_version='0.3.0rc3',
                published_at=datetime(2026, 8, 3, 17, tzinfo=UTC),
            ),
            artifact_store=InMemoryArtifactStore(),
        )


def test_p3_s31_native_models_are_consumed_without_copying_contracts():
    fixture = _p3_root() / 'tests/fixtures/capabilities/products/s31'
    bundle = json.loads((fixture / 'm01_output.json').read_text())['outputs']['p9_evaluation_evidence_bundle']
    manifest = json.loads((fixture / 'm02_output.json').read_text())['outputs']['p9_context_learning_handoff_manifest']
    # The historical JSON example predates three fields that are mandatory in the
    # final P3 model; enrich the example without changing its contract identity.
    for commitment in bundle['commitments']:
        commitment.setdefault('person_id', 'person-fixture')
        commitment.setdefault('belief_value', 0.25)
        commitment.setdefault('confidence', 0.75)
    receipt = validate_p3_evaluation_boundary(
        evaluation_bundle=bundle,
        context_manifest=manifest,
        checked_at=datetime(2026, 8, 4, 10, tzinfo=UTC),
        p3_source_root=_p3_root(),
    )
    assert receipt.phase_id == 'P3'
    assert receipt.state in {CompatibilityState.COMPATIBLE, CompatibilityState.COMPATIBLE_LIMITED}
    assert receipt.run_id == bundle['run_id']


def test_p3_retro_context_is_context_only_and_future_valid():
    package, manifest = build_p3_retro_context_package(
        memory_update_id='memory-update-1',
        retro_package_id='retro-package-1',
        created_at=datetime(2026, 8, 4, 10, tzinfo=UTC),
        valid_from=datetime(2026, 8, 5, 10, tzinfo=UTC),
        source_backtest_id='backtest-1',
        lineage_id='lineage-1',
        memory_items=[{'memory_item_id': 'm1', 'claim': 'abstract failure pattern'}],
        hypothesis_items=[],
        evidence_items=[],
        context_tags=['research'],
    )
    assert package['agent_instruction_updates'] == []
    assert 'direct_model_change' not in package
    assert manifest['lineage_id'] == package['lineage_id']


def _p8_ref(artifact_id: str, at: datetime):
    from quant_pipeline.phase_08_contracts.common import ArtifactReference
    return ArtifactReference(
        artifact_id=artifact_id,
        artifact_type='authorization',
        schema_version='1.0.0',
        contract_version='1.0.0',
        content_sha256='a' * 64,
        available_at=at,
    )


def test_p9_p0_materializer_builds_exact_current_p8_feedback():
    from quant_pipeline.phase_08_contracts.enums import FeedbackEffectType, FeedbackRecommendationStatus
    from quant_pipeline.phase_08_contracts.p9 import (
        NumericAuthorizationBound,
        P0PolicyAuthorizationV1,
        P9FeedbackRecommendationV1,
    )
    at = datetime(2026, 8, 4, 10, tzinfo=UTC)
    candidate = {
        'feedback_id': 'feedback-1',
        'target_policy_id': 'risk.max_gross',
        'source_cycle': {'cycle_id': 'cycle-1', 'ordinal': 1},
    }
    recommendation = P9FeedbackRecommendationV1(
        recommendation_id='recommendation-1',
        feedback_id='feedback-1',
        target_policy_id='risk.max_gross',
        effect_type=FeedbackEffectType.RISK_LIMIT_POLICY_FEEDBACK,
        status=FeedbackRecommendationStatus.PROMOTED,
        source_cycle_sequence=1,
        available_at=at,
    )
    authorization = P0PolicyAuthorizationV1(
        authorization_id='authorization-1',
        feedback_id='feedback-1',
        target_policy_id='risk.max_gross',
        effect_type=FeedbackEffectType.RISK_LIMIT_POLICY_FEEDBACK,
        valid_from_sequence=2,
        numeric_bounds=(NumericAuthorizationBound(field_name='new_limit', minimum=Decimal('0'), maximum=Decimal('2')),),
        available_at=at,
    )
    feedback = materialize_p8_promoted_feedback(
        p9_candidate=candidate,
        concrete_payload={'limit_name': 'max_gross', 'new_limit': '1.25', 'unit': 'ratio'},
        p9_recommendation=recommendation,
        p0_authorization=authorization,
        p8_effect_type='RISK_LIMIT_POLICY_FEEDBACK',
        p9_recommendation_ref=_p8_ref('recommendation-ref', at),
        p0_authorization_ref=_p8_ref('authorization-ref', at),
        target_cycle_id='cycle-2',
        target_cycle_sequence=2,
        effective_from_sequence=2,
        idempotency_key='feedback-1-cycle-2',
        available_at=at,
    )
    assert feedback.effect_type.value == 'RISK_LIMIT_POLICY_FEEDBACK'
    assert str(feedback.payload.new_limit) == '1.25'
    assert feedback.target_cycle_sequence == 2


def test_materialized_feedback_passes_real_p8_loader_and_idempotency():
    from quant_pipeline.phase_08_contracts.canonical import raw_sha256
    from quant_pipeline.phase_08_portfolio_control.s01_boundary.module_support import verify_model_embedded_hash
    from quant_pipeline.phase_08_contracts.common import ArtifactReference
    from quant_pipeline.phase_08_contracts.enums import (
        FeedbackEffectType,
        FeedbackRecommendationStatus,
        RuntimeMode,
    )
    from quant_pipeline.phase_08_contracts.p9 import (
        NumericAuthorizationBound,
        P0PolicyAuthorizationV1,
        P9FeedbackRecommendationV1,
    )
    from quant_pipeline.phase_08_portfolio_control.s01_boundary.adapters import (
        InMemoryArtifactStore as P8ArtifactStore,
        InMemoryIdempotencyStore,
    )
    from quant_pipeline.phase_08_portfolio_control.s01_boundary.context import S1ExecutionContext
    from quant_pipeline.phase_08_portfolio_control.s01_boundary.modules.m04_promoted_portfolio_feedback_loader import (
        run_module as run_p8_feedback_loader,
    )

    at = datetime(2026, 8, 4, 10, tzinfo=UTC)
    recommendation = P9FeedbackRecommendationV1(
        recommendation_id='recommendation-loader-1',
        feedback_id='feedback-loader-1',
        target_policy_id='risk.max_gross',
        effect_type=FeedbackEffectType.RISK_LIMIT_POLICY_FEEDBACK,
        status=FeedbackRecommendationStatus.PROMOTED,
        source_cycle_sequence=1,
        available_at=at,
    )
    authorization = P0PolicyAuthorizationV1(
        authorization_id='authorization-loader-1',
        feedback_id='feedback-loader-1',
        target_policy_id='risk.max_gross',
        effect_type=FeedbackEffectType.RISK_LIMIT_POLICY_FEEDBACK,
        valid_from_sequence=2,
        expires_after_sequence=3,
        numeric_bounds=(
            NumericAuthorizationBound(
                field_name='new_limit', minimum=Decimal('0'), maximum=Decimal('2')
            ),
        ),
        available_at=at,
    )
    recommendation_raw = recommendation.model_dump_json().encode('utf-8')
    authorization_raw = authorization.model_dump_json().encode('utf-8')
    recommendation_ref = ArtifactReference(
        artifact_id='recommendation-loader-1.json',
        artifact_type='P9_FEEDBACK_RECOMMENDATION_V1',
        schema_version='1.0.0',
        contract_version='P9_FEEDBACK_RECOMMENDATION_V1',
        content_sha256=raw_sha256(recommendation_raw),
        available_at=at,
    )
    authorization_ref = ArtifactReference(
        artifact_id='authorization-loader-1.json',
        artifact_type='P0_POLICY_AUTHORIZATION_V1',
        schema_version='1.0.0',
        contract_version='P0_POLICY_AUTHORIZATION_V1',
        content_sha256=raw_sha256(authorization_raw),
        available_at=at,
    )
    feedback = materialize_p8_promoted_feedback(
        p9_candidate={
            'feedback_id': 'feedback-loader-1',
            'target_policy_id': 'risk.max_gross',
            'source_cycle': {'cycle_id': 'cycle-1', 'ordinal': 1},
        },
        concrete_payload={'limit_name': 'max_gross', 'new_limit': '1.25', 'unit': 'ratio'},
        p9_recommendation=recommendation,
        p0_authorization=authorization,
        p8_effect_type='RISK_LIMIT_POLICY_FEEDBACK',
        p9_recommendation_ref=recommendation_ref,
        p0_authorization_ref=authorization_ref,
        target_cycle_id='cycle-2',
        target_cycle_sequence=2,
        effective_from_sequence=2,
        idempotency_key='feedback-loader-1-cycle-2',
        available_at=at,
    )
    verify_model_embedded_hash(feedback)
    feedback_raw = feedback.model_dump_json().encode('utf-8')
    feedback_ref = ArtifactReference(
        artifact_id='feedback-loader-1.json',
        artifact_type='P9_TO_P8_PROMOTED_FEEDBACK_V1',
        schema_version='1.0.0',
        contract_version='P9_TO_P8_PROMOTED_FEEDBACK_V1',
        content_sha256=raw_sha256(feedback_raw),
        available_at=at,
    )
    artifact_store = P8ArtifactStore(
        {
            recommendation_ref.artifact_id: recommendation_raw,
            authorization_ref.artifact_id: authorization_raw,
            feedback_ref.artifact_id: feedback_raw,
        }
    )
    context = S1ExecutionContext(
        run_id='run-loader-1',
        cycle_id='cycle-2',
        cycle_sequence=2,
        decision_time=at + timedelta(minutes=30),
        market_cutoff_at=at,
        computed_at=at + timedelta(minutes=31),
        runtime_mode=RuntimeMode.BACKTEST,
    )
    idempotency_store = InMemoryIdempotencyStore()
    first = run_p8_feedback_loader(
        (feedback_ref,),
        store=artifact_store,
        idempotency_store=idempotency_store,
        context=context,
    )
    second = run_p8_feedback_loader(
        (feedback_ref,),
        store=artifact_store,
        idempotency_store=idempotency_store,
        context=context,
    )
    assert first.feedback_context.item_receipts[0].status.value == 'APPLIED'
    assert second.feedback_context.item_receipts[0].status.value == 'ALREADY_APPLIED'


def test_p8_materializer_rejects_missing_source_cycle_and_naive_time():
    from quant_pipeline.phase_08_contracts.enums import FeedbackEffectType, FeedbackRecommendationStatus
    from quant_pipeline.phase_08_contracts.p9 import (
        P0PolicyAuthorizationV1,
        P9FeedbackRecommendationV1,
    )
    at = datetime(2026, 8, 4, 10, tzinfo=UTC)
    recommendation = P9FeedbackRecommendationV1(
        recommendation_id='recommendation-invalid-1',
        feedback_id='feedback-invalid-1',
        target_policy_id='risk.max_gross',
        effect_type=FeedbackEffectType.RISK_LIMIT_POLICY_FEEDBACK,
        status=FeedbackRecommendationStatus.PROMOTED,
        source_cycle_sequence=1,
        available_at=at,
    )
    authorization = P0PolicyAuthorizationV1(
        authorization_id='authorization-invalid-1',
        feedback_id='feedback-invalid-1',
        target_policy_id='risk.max_gross',
        effect_type=FeedbackEffectType.RISK_LIMIT_POLICY_FEEDBACK,
        valid_from_sequence=2,
        available_at=at,
    )
    kwargs = dict(
        concrete_payload={'limit_name': 'max_gross', 'new_limit': '1.25', 'unit': 'ratio'},
        p9_recommendation=recommendation,
        p0_authorization=authorization,
        p8_effect_type='RISK_LIMIT_POLICY_FEEDBACK',
        p9_recommendation_ref=_p8_ref('recommendation-invalid-ref', at),
        p0_authorization_ref=_p8_ref('authorization-invalid-ref', at),
        target_cycle_id='cycle-2',
        target_cycle_sequence=2,
        effective_from_sequence=2,
        idempotency_key='feedback-invalid-1-cycle-2',
    )
    with pytest.raises(ContractMismatchError, match='source_cycle'):
        materialize_p8_promoted_feedback(
            p9_candidate={'feedback_id': 'feedback-invalid-1', 'target_policy_id': 'risk.max_gross'},
            available_at=at,
            **kwargs,
        )
    with pytest.raises(ContractMismatchError, match='timezone-aware'):
        materialize_p8_promoted_feedback(
            p9_candidate={
                'feedback_id': 'feedback-invalid-1',
                'target_policy_id': 'risk.max_gross',
                'source_cycle': {'cycle_id': 'cycle-1', 'ordinal': 1},
            },
            available_at=datetime(2026, 8, 4, 10),
            **kwargs,
        )


def test_all_qualified_phase_snapshots_match_frozen_fingerprints():
    baseline = _baseline_root()
    roots = {
        'P0': baseline / 'phase_00_zero_trust/phase_00_zero_trust_guardian_agent_package_RC4_1',
        'P1': baseline / 'phase_01_ingestion/phase_01_ingestion_agent_package_RC4_1',
        'P2': baseline / 'phase_02_extracted/phase_02_quality_pit_agent_package_RC4_1',
        'P3': _p3_root(),
        'P4': baseline / 'phase_04_extracted/phase_04_feature_base_agent_package_RC4_1',
        'P5': P5_ROOT,
        'P6': P6_ROOT,
        'P7': P7_ROOT,
        'P8': P8_ROOT,
    }
    checked_at = datetime(2026, 8, 4, 10, tzinfo=UTC)
    receipts = {
        phase_id: verify_phase_package_fingerprint(
            phase_id=phase_id, package_root=root, checked_at=checked_at
        )
        for phase_id, root in roots.items()
    }
    assert set(receipts) == {f'P{i}' for i in range(9)}
    assert all(receipt.source_payload_sha256 for receipt in receipts.values())
    assert receipts['P3'].state is CompatibilityState.COMPATIBLE_PROCESS_ISOLATED
    assert receipts['P6'].state is CompatibilityState.COMPATIBLE_GOVERNED
    assert receipts['P8'].state is CompatibilityState.COMPATIBLE_LIMITED


def test_p6_snapshot_confirms_feedback_is_governed_not_direct():
    receipt = verify_phase_package_fingerprint(
        phase_id='P6',
        package_root=P6_ROOT,
        checked_at=datetime(2026, 8, 4, 10, tzinfo=UTC),
    )
    assert receipt.state is CompatibilityState.COMPATIBLE_GOVERNED
    assert receipt.limitations
    assert any('P0-mediated' in item for item in receipt.limitations)


def test_p0_report_set_is_self_verifying():
    reports = build_p0_control_plane_reports(
        run_id='run-1', cycle_id='cycle-1', backtest_id='backtest-1',
        created_at=datetime(2026, 8, 4, 10, tzinfo=UTC),
        package_version='0.1.0rc4',
        module_ids=('P9.S1.M01', 'P9.S10.M04'),
        artifact_records=({'artifact_id': 'a1', 'content_sha256': 'b' * 64},),
        test_summary={'status': 'PASS', 'passed': 1, 'failed': 0},
        code_quality_summary={'status': 'PASS'},
        lineage_summary={'status': 'PASS', 'root_ids': ['a1']},
    )
    assert reports.dashboard_phase_payload['production_authorized'] is False
    assert reports.phase_manifest['phase_id'] == 'P9'


def test_legacy_feedback_reports_preserve_exact_required_fields():
    header = LegacyFeedbackHeader(
        feedback_id='f1', experiment_id='e1', backtest_id='b1',
        created_at=datetime(2026, 8, 4, 10, tzinfo=UTC), target_phase='P5',
        recommended_action='RESEARCH', severity='INFO', valid_for_next_cycle_only=True,
    )
    signal = SignalFeedbackReport(
        header=header, target_module='P5.S1.M01', forecast_error_summary={},
        calibration_error={}, regime_performance_breakdown={}, ood_failure_summary={},
        drift_failure_summary={}, model_stability_score=0.5,
    ).to_wire()
    ranking = RankingFeedbackReport(
        header=header.model_copy(update={'target_phase': 'P7'}), rank_ic_summary={},
        ndcg_at_k_summary={}, top_k_hit_rate=0.5, blocked_candidate_review={},
        bad_candidate_accepted_review={}, score_head_ablation_summary={},
        safety_gate_effectiveness={},
    ).to_wire()
    portfolio = PortfolioFeedbackReport(
        header=header.model_copy(update={'target_phase': 'P8'}), sizing_stability_summary={},
        execution_quality_summary={}, cost_slippage_error_summary={},
        risk_limit_breach_summary={}, entropy_effectiveness_summary={},
        margin_usage_summary={}, short_option_policy_review={},
    ).to_wire()
    assert signal['valid_for_next_cycle_only'] is True and signal['target_module'] == 'P5.S1.M01'
    assert ranking['target_phase'] == 'P7' and 'rank_ic_summary' in ranking
    assert portfolio['target_phase'] == 'P8' and 'execution_quality_summary' in portfolio


def test_legacy_feedback_is_accepted_by_real_p5_p7_p8_consumers():
    from quant_pipeline.phase_09.compatibility.legacy_consumers import validate_legacy_feedback_consumer
    baseline = _baseline_root()
    header = LegacyFeedbackHeader(
        feedback_id='feedback-consumer-1', experiment_id='experiment-1', backtest_id='backtest-1',
        created_at=datetime(2026, 8, 4, 10, tzinfo=UTC), target_phase='P5',
        recommended_action='RESEARCH', severity='INFO', valid_for_next_cycle_only=True,
    )
    signal = SignalFeedbackReport(
        header=header, target_module='P5.S1.M01', forecast_error_summary={},
        calibration_error={}, regime_performance_breakdown={}, ood_failure_summary={},
        drift_failure_summary={}, model_stability_score=0.5,
    ).to_wire()
    ranking = RankingFeedbackReport(
        header=header.model_copy(update={'target_phase': 'P7'}), rank_ic_summary={},
        ndcg_at_k_summary={}, top_k_hit_rate=0.5, blocked_candidate_review={},
        bad_candidate_accepted_review={}, score_head_ablation_summary={}, safety_gate_effectiveness={},
    ).to_wire()
    portfolio = PortfolioFeedbackReport(
        header=header.model_copy(update={'target_phase': 'P8'}), sizing_stability_summary={},
        execution_quality_summary={}, cost_slippage_error_summary={}, risk_limit_breach_summary={},
        entropy_effectiveness_summary={}, margin_usage_summary={}, short_option_policy_review={},
    ).to_wire()
    roots = {
        'P5': baseline / 'phase_05_extracted/phase_05_underlying_forecasts_agent_package_RC4_1',
        'P7': baseline / 'phase_07_extracted/phase_07_ranking_agent_package_RC4_1',
        'P8': baseline / 'phase_08_extracted/phase_08_portfolio_backtest_agent_package_RC4_1',
    }
    assert validate_legacy_feedback_consumer(phase_id='P5', feedback_record=signal, phase_package_root=roots['P5'])['module_id'] == 'P5.S1.M02'
    assert validate_legacy_feedback_consumer(phase_id='P7', feedback_record=ranking, phase_package_root=roots['P7'])['module_id'] == 'P7.S1.M02'
    assert validate_legacy_feedback_consumer(phase_id='P8', feedback_record=portfolio, phase_package_root=roots['P8'])['module_id'] == 'P8.S1.M02'


def test_p0_reports_are_accepted_by_real_p0_normalizers():
    p0_root = _baseline_root() / 'phase_00_zero_trust/phase_00_zero_trust_guardian_agent_package_RC4_1'
    reports = build_p0_control_plane_reports(
        run_id='run-p0-native',
        cycle_id='cycle-p0-native',
        backtest_id='backtest-p0-native',
        created_at=datetime(2026, 8, 4, 10, tzinfo=UTC),
        package_version='0.1.0rc4',
        module_ids=('P9.S1.M01', 'P9.S10.M04'),
        artifact_records=({'artifact_id': 'artifact-p0-1', 'content_sha256': 'd' * 64},),
        test_summary={'passed': 585, 'failed': 0, 'skipped': 1},
        code_quality_summary={'status': 'PASS'},
        lineage_summary={'status': 'PASS'},
    )
    normalized = validate_p0_control_plane_consumer(reports=reports, p0_source_root=p0_root)
    assert normalized['test_run_report']['status'] == 'PARTIAL'
    assert normalized['test_run_report']['total_tests'] == 586
    assert normalized['dashboard_phase_payload']['status'] == 'FAIL'
    assert normalized['dashboard_phase_payload']['release_blocking'] is True


def test_p0_reports_match_global_required_fields():
    reports = build_p0_control_plane_reports(
        run_id='run-2', cycle_id='cycle-2', backtest_id='backtest-2',
        created_at=datetime(2026, 8, 4, 10, tzinfo=UTC), package_version='0.1.0rc4',
        module_ids=('P9.S1.M01',), artifact_records=({'artifact_id': 'a2', 'content_sha256': 'c' * 64},),
        test_summary={'status': 'PASS', 'passed': 575, 'failed': 0, 'skipped': 0},
        code_quality_summary={'status': 'PASS'}, lineage_summary={'status': 'PASS'},
    )
    test_required = {
        'test_run_id', 'phase_id', 'package_version', 'pipeline_version', 'executed_at',
        'total_tests', 'passed_tests', 'failed_tests', 'skipped_tests', 'status',
    }
    dashboard_required = {
        'phase_id', 'phase_name', 'run_id', 'status', 'inputs_received', 'outputs_emitted',
        'tests_passed', 'tests_failed', 'artifact_hash_coverage', 'schema_validation_status',
        'forbidden_connection_status',
    }
    assert test_required <= set(reports.test_run_report)
    assert dashboard_required <= set(reports.dashboard_phase_payload)


def _current_p3_bundle_manifest():
    fixture = _p3_root() / 'tests/fixtures/capabilities/products/s31'
    bundle = json.loads((fixture / 'm01_output.json').read_text())['outputs']['p9_evaluation_evidence_bundle']
    manifest = json.loads((fixture / 'm02_output.json').read_text())['outputs']['p9_context_learning_handoff_manifest']
    for commitment in bundle['commitments']:
        commitment.setdefault('person_id', 'person-fixture')
        commitment.setdefault('belief_value', 0.25)
        commitment.setdefault('confidence', 0.75)
    return bundle, manifest


def test_p3_belief_feedback_round_trip_through_real_consumer():
    bundle, manifest = _current_p3_bundle_manifest()
    package, handoff = build_p3_belief_feedback(
        evaluation_bundle=bundle,
        context_manifest=manifest,
        outcomes=(),
        evaluated_at=datetime(2026, 7, 26, 12, tzinfo=UTC),
        source_cycle_id=1,
        experience_available_from_cycle=2,
        p3_source_root=_p3_root(),
    )
    snapshot = json.loads((_p3_root() / 'fixtures/integration/governance_outputs.json').read_text())['phase3_run_snapshot']
    result = validate_p3_belief_feedback_consumer(
        package=package,
        manifest=handoff,
        phase3_run_snapshot=snapshot,
        current_cycle_id=2,
        processed_at=datetime(2026, 7, 27, 12, tzinfo=UTC),
        p3_source_root=_p3_root(),
    )
    assert result['status'] == 'NO_MATURED_FEEDBACK'
    assert result['feedback_items'] == []


def test_p3_context_round_trip_through_real_retro_consumer():
    import yaml
    package, manifest = build_p3_retro_context_package(
        memory_update_id='memory-roundtrip-1', retro_package_id='retro-roundtrip-1',
        created_at=datetime(2026, 7, 26, tzinfo=UTC),
        valid_from=datetime(2026, 7, 28, tzinfo=UTC),
        source_backtest_id='backtest-1', lineage_id='lineage-roundtrip-1',
        memory_items=[{'memory_item_id': 'm1', 'claim': 'abstract relation'}],
        hypothesis_items=[], evidence_items=[], context_tags=['research'],
    )
    snapshot = json.loads((_p3_root() / 'fixtures/integration/governance_outputs.json').read_text())['phase3_run_snapshot']
    policy = yaml.safe_load((_p3_root() / 'config/governance/RETRO_PATCH_COMPATIBILITY_CONFIG.yaml').read_text())
    result = validate_p3_retro_context_consumer(
        package=package, manifest=manifest, phase3_run_snapshot=snapshot, policy=policy,
        current_cycle_id=2, processed_at=datetime(2026, 7, 27, 12, tzinfo=UTC),
        p3_source_root=_p3_root(),
    )
    assert result['status'] == 'NO_PATCH'
    assert result['patch'] is None
