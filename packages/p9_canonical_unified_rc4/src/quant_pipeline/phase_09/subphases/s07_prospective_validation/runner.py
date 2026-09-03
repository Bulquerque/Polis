"""Typed orchestration for the eight P9.S7 modules."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from .bundle import (
    Clock,
    ProspectiveMonitoringBundle,
    ProspectiveMonitoringPayload,
    S7ExecutionRequest,
    validate_materialization_receipt,
)
from .canonical import payload_sha256
from .contracts import (
    IntegrityEnvelope,
    ModuleExecutionReceipt,
    ModuleStatus,
    S7SubphaseExecutionReceipt,
)
from .m01_prequential import PrequentialStreamResult, build_prequential_stream
from .m02_shadow import (
    ShadowComparabilityReceipt,
    ShadowExecutionPlan,
    build_shadow_execution_plan,
    evaluate_shadow_comparability,
)
from .m03_scoring import OnlineScoringResult, score_prequential_records
from .m04_conformal import ConformalMonitoringResult, monitor_adaptive_conformal
from .m05_drift import DriftQualificationResult, detect_multichannel_drift
from .m06_sequential import SequentialModelSet, compare_policies_anytime
from .m07_rollback import RollbackRecommendation, evaluate_live_health
from .m08_reality_gap import RealityGapResult, evaluate_reality_gap

MODULE_IDS = tuple(f"P9.S7.M0{index}" for index in range(1, 9))
ModuleIdLiteral = Literal[
    "P9.S7.M01",
    "P9.S7.M02",
    "P9.S7.M03",
    "P9.S7.M04",
    "P9.S7.M05",
    "P9.S7.M06",
    "P9.S7.M07",
    "P9.S7.M08",
]


class S7Pipeline:
    """Execute P9.S7 in frozen order; scientific logic remains in modules."""

    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock or Clock()

    def run(self, request: S7ExecutionRequest) -> ProspectiveMonitoringBundle:
        validate_materialization_receipt(request)
        receipts: list[ModuleExecutionReceipt] = []
        stream = self._run_m01(request, receipts)
        shadow_plan, shadow_receipt = self._run_m02(request, stream, receipts)
        scoring = self._run_m03(request, stream, receipts)
        conformal = self._run_m04(request, scoring, receipts)
        drift = self._run_m05(request, scoring, receipts)
        comparison = self._run_m06(request, scoring, receipts)
        rollback = self._run_m07(request, drift, comparison, receipts)
        reality_gap = self._run_m08(request, shadow_receipt, rollback, receipts)
        return self._build_bundle(
            request=request,
            receipts=tuple(receipts),
            stream=stream,
            shadow_plan=shadow_plan,
            shadow_receipt=shadow_receipt,
            scoring=scoring,
            conformal=conformal,
            drift=drift,
            comparison=comparison,
            rollback=rollback,
            reality_gap=reality_gap,
        )

    def _run_m01(
        self,
        request: S7ExecutionRequest,
        receipts: list[ModuleExecutionReceipt],
    ) -> PrequentialStreamResult:
        result, receipt = self._run_module(
            "P9.S7.M01",
            ("predictions", "outcomes"),
            lambda: build_prequential_stream(
                request.predictions,
                request.outcomes,
                request.existing_records,
            ),
        )
        receipts.append(receipt)
        return result  # type: ignore[return-value]

    def _run_m02(
        self,
        request: S7ExecutionRequest,
        stream: PrequentialStreamResult,
        receipts: list[ModuleExecutionReceipt],
    ) -> tuple[ShadowExecutionPlan, ShadowComparabilityReceipt]:
        result, receipt = self._run_module(
            "P9.S7.M02",
            (stream.receipt.stream_sha256,),
            lambda: build_shadow_execution_plan(
                stream.records,
                request.champion_policy,
                request.challenger_policies,
                request.allowed_policy_ids,
            ),
        )
        plan = result  # type: ignore[assignment]
        comparability = evaluate_shadow_comparability(
            plan,
            request.policy_execution_outputs,
        )
        receipts.append(
            self._replace_output_receipt(
                receipt,
                "shadow_comparability",
                comparability.receipt_sha256,
            )
        )
        return plan, comparability

    def _run_m03(
        self,
        request: S7ExecutionRequest,
        stream: PrequentialStreamResult,
        receipts: list[ModuleExecutionReceipt],
    ) -> OnlineScoringResult:
        result, receipt = self._run_module(
            "P9.S7.M03",
            (stream.receipt.stream_sha256,),
            lambda: score_prequential_records(stream.records, request.scoring_policy),
        )
        receipts.append(receipt)
        return result  # type: ignore[return-value]

    def _run_m04(
        self,
        request: S7ExecutionRequest,
        scoring: OnlineScoringResult,
        receipts: list[ModuleExecutionReceipt],
    ) -> ConformalMonitoringResult:
        result, receipt = self._run_module(
            "P9.S7.M04",
            (scoring.score_panel_sha256,),
            lambda: monitor_adaptive_conformal(
                request.conformal_observations,
                request.conformal_policy,
            ),
            specialist=True,
        )
        receipts.append(receipt)
        return result  # type: ignore[return-value]

    def _run_m05(
        self,
        request: S7ExecutionRequest,
        scoring: OnlineScoringResult,
        receipts: list[ModuleExecutionReceipt],
    ) -> DriftQualificationResult:
        result, receipt = self._run_module(
            "P9.S7.M05",
            (scoring.score_panel_sha256,),
            lambda: detect_multichannel_drift(
                request.drift_observations,
                request.drift_policies,
                request.minimum_confirming_drift_channels,
            ),
        )
        receipts.append(receipt)
        return result  # type: ignore[return-value]

    def _run_m06(
        self,
        request: S7ExecutionRequest,
        scoring: OnlineScoringResult,
        receipts: list[ModuleExecutionReceipt],
    ) -> SequentialModelSet:
        result, receipt = self._run_module(
            "P9.S7.M06",
            (scoring.score_panel_sha256,),
            lambda: compare_policies_anytime(
                request.paired_loss_observations,
                request.sequential_comparison_policy,
                request.offline_model_set,
            ),
        )
        receipts.append(receipt)
        return result  # type: ignore[return-value]

    def _run_m07(
        self,
        request: S7ExecutionRequest,
        drift: DriftQualificationResult,
        comparison: SequentialModelSet,
        receipts: list[ModuleExecutionReceipt],
    ) -> RollbackRecommendation:
        result, receipt = self._run_module(
            "P9.S7.M07",
            (drift.result_sha256, comparison.result_sha256),
            lambda: evaluate_live_health(
                request.live_execution_metrics,
                drift.agreement,
                comparison,
                request.stress_capacity_qualification,
                request.rollback_policy,
            ),
        )
        receipts.append(receipt)
        return result  # type: ignore[return-value]

    def _run_m08(
        self,
        request: S7ExecutionRequest,
        shadow_receipt: ShadowComparabilityReceipt,
        rollback: RollbackRecommendation,
        receipts: list[ModuleExecutionReceipt],
    ) -> RealityGapResult:
        result, receipt = self._run_module(
            "P9.S7.M08",
            (shadow_receipt.receipt_sha256, rollback.result_sha256),
            lambda: evaluate_reality_gap(
                request.stage_execution_records,
                request.reality_gap_policy,
            ),
        )
        receipts.append(receipt)
        return result  # type: ignore[return-value]

    def _build_bundle(
        self,
        *,
        request: S7ExecutionRequest,
        receipts: tuple[ModuleExecutionReceipt, ...],
        stream: PrequentialStreamResult,
        shadow_plan: ShadowExecutionPlan,
        shadow_receipt: ShadowComparabilityReceipt,
        scoring: OnlineScoringResult,
        conformal: ConformalMonitoringResult,
        drift: DriftQualificationResult,
        comparison: SequentialModelSet,
        rollback: RollbackRecommendation,
        reality_gap: RealityGapResult,
    ) -> ProspectiveMonitoringBundle:
        subphase_receipt = self._build_subphase_receipt(receipts)
        payload = ProspectiveMonitoringPayload(
            header=request.header,
            upstream_bundle_sha256s=(
                request.upstream.foundation_bundle.content_sha256,
                request.upstream.backtest_metrics_bundle.content_sha256,
                request.upstream.robustness_stress_bundle.content_sha256,
            ),
            prequential_stream=stream,
            shadow_plan=shadow_plan,
            shadow_comparability=shadow_receipt,
            online_scoring=scoring,
            conformal_monitoring=conformal,
            drift_qualification=drift,
            sequential_model_set=comparison,
            rollback_recommendation=rollback,
            reality_gap=reality_gap,
            module_receipts=receipts,
            subphase_receipt=subphase_receipt,
            limitations=tuple(conformal.limitations),
        )
        return ProspectiveMonitoringBundle(
            payload=payload,
            integrity=IntegrityEnvelope(payload_sha256=payload_sha256(payload)),
        )

    def _build_subphase_receipt(
        self,
        receipts: tuple[ModuleExecutionReceipt, ...],
    ) -> S7SubphaseExecutionReceipt:
        status = _aggregate_subphase_status(receipts)
        output_ids = tuple(
            output
            for receipt in receipts
            for output in receipt.output_artifact_ids
        )
        provisional = _subphase_receipt_without_integrity(
            receipts,
            status,
            output_ids,
        )
        digest = payload_sha256(provisional.model_dump(exclude={"integrity"}))
        return provisional.model_copy(
            update={"integrity": IntegrityEnvelope(payload_sha256=digest)}
        )

    def _run_module(
        self,
        module_id: ModuleIdLiteral,
        input_ids: tuple[str, ...],
        operation: Callable[[], object],
        specialist: bool = False,
    ) -> tuple[object, ModuleExecutionReceipt]:
        started = self._clock()
        result = operation()
        completed = self._clock()
        result_hash = payload_sha256(result)  # type: ignore[arg-type]
        status, limitations = _specialist_status(result, specialist)
        output_id = f"{module_id}:{result_hash[:16]}"
        diagnostics = {
            "module_id": module_id,
            "result_type": type(result).__name__,
            "result_sha256": result_hash,
        }
        provisional = ModuleExecutionReceipt(
            module_id=module_id,
            status=status,
            input_artifact_ids=input_ids,
            output_artifact_ids=(output_id,),
            limitations=limitations,
            started_at=started,
            completed_at=completed,
            diagnostics_sha256=payload_sha256(diagnostics),
            integrity=IntegrityEnvelope(payload_sha256="0" * 64),
        )
        digest = payload_sha256(provisional.model_dump(exclude={"integrity"}))
        receipt = provisional.model_copy(
            update={"integrity": IntegrityEnvelope(payload_sha256=digest)}
        )
        return result, receipt

    @staticmethod
    def _replace_output_receipt(
        receipt: ModuleExecutionReceipt,
        label: str,
        digest: str,
    ) -> ModuleExecutionReceipt:
        output_artifact_id = f"{receipt.module_id}:{label}:{digest[:16]}"
        updated = receipt.model_copy(
            update={"output_artifact_ids": (output_artifact_id,)}
        )
        receipt_digest = payload_sha256(updated.model_dump(exclude={"integrity"}))
        return updated.model_copy(
            update={"integrity": IntegrityEnvelope(payload_sha256=receipt_digest)}
        )


def _specialist_status(
    result: object,
    specialist: bool,
) -> tuple[ModuleStatus, tuple[str, ...]]:
    if not specialist or getattr(result, "availability", None) is None:
        return ModuleStatus.SUCCESS, ()
    availability = str(getattr(result, "availability"))
    limitations = tuple(getattr(result, "limitations", ()))
    if availability.endswith("UNAVAILABLE"):
        return ModuleStatus.UNAVAILABLE, limitations
    if availability.endswith("LIMITED"):
        return ModuleStatus.LIMITED, limitations
    return ModuleStatus.SUCCESS, limitations


def _aggregate_subphase_status(
    receipts: tuple[ModuleExecutionReceipt, ...],
) -> ModuleStatus:
    statuses = {receipt.status for receipt in receipts}
    if ModuleStatus.FAILED in statuses:
        return ModuleStatus.FAILED
    if ModuleStatus.INVALID in statuses:
        return ModuleStatus.INVALID
    if statuses <= {ModuleStatus.SUCCESS}:
        return ModuleStatus.SUCCESS
    allowed = {ModuleStatus.SUCCESS, ModuleStatus.LIMITED, ModuleStatus.UNAVAILABLE}
    if statuses <= allowed:
        return ModuleStatus.LIMITED
    return ModuleStatus.INSUFFICIENT_EVIDENCE


def _subphase_receipt_without_integrity(
    receipts: tuple[ModuleExecutionReceipt, ...],
    status: ModuleStatus,
    output_ids: tuple[str, ...],
) -> S7SubphaseExecutionReceipt:
    return S7SubphaseExecutionReceipt(
        expected_module_ids=MODULE_IDS,
        module_receipts=receipts,
        status=status,
        output_artifact_ids=output_ids,
        integrity=IntegrityEnvelope(payload_sha256="0" * 64),
    )


__all__ = [
    "Clock",
    "ProspectiveMonitoringBundle",
    "ProspectiveMonitoringPayload",
    "S7ExecutionRequest",
    "S7Pipeline",
]
