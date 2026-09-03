"""Imperative orchestration shell for P9.S8."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from quant_pipeline.phase_09.subphases.s07_prospective_validation.contracts import (
    IntegrityEnvelope,
    ModuleStatus,
)

from .bundle import (
    ProspectiveAttributionBundle,
    ProspectiveAttributionPayload,
    Clock,
    S8ExecutionRequest,
)
from .canonical import payload_sha256
from .contracts import (
    AttributionQuality,
    S8ModuleExecutionReceipt,
    S8SubphaseExecutionReceipt,
)
from .m01_forecast_attribution import attribute_forecast_components
from .m02_payoff_attribution import evaluate_payoff_fidelity
from .m03_ranking_attribution import evaluate_ranking
from .m04_portfolio_attribution import attribute_portfolio_construction
from .m05_execution_attribution import attribute_execution_and_lifecycle
from .m06_option_attribution import attribute_option_pnl
from .m07_counterfactual import evaluate_counterfactual_policy
from .m08_reconciliation import reconcile_attribution

ModuleIdLiteral = Literal[
    "P9.S8.M01",
    "P9.S8.M02",
    "P9.S8.M03",
    "P9.S8.M04",
    "P9.S8.M05",
    "P9.S8.M06",
    "P9.S8.M07",
    "P9.S8.M08",
]
EXPECTED_MODULES: tuple[ModuleIdLiteral, ...] = (
    "P9.S8.M01",
    "P9.S8.M02",
    "P9.S8.M03",
    "P9.S8.M04",
    "P9.S8.M05",
    "P9.S8.M06",
    "P9.S8.M07",
    "P9.S8.M08",
)


class S8Pipeline:
    """Run the eight S8 engines without hiding their scientific logic."""

    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock or Clock()

    def run(self, request: S8ExecutionRequest) -> ProspectiveAttributionBundle:
        receipts: list[S8ModuleExecutionReceipt] = []
        forecast = self._execute(
            "P9.S8.M01",
            (request.s7_bundle.payload.online_scoring.score_panel_sha256,),
            lambda: attribute_forecast_components(
                request.forecast_observations,
                request.forecast_policy,
            ),
            receipts,
        )
        payoff = self._execute(
            "P9.S8.M02",
            (request.upstream.foundation_bundle.content_sha256,),
            lambda: evaluate_payoff_fidelity(
                request.payoff_scenario_points,
                request.candidate_outcomes,
                request.payoff_policy,
            ),
            receipts,
        )
        ranking = self._execute(
            "P9.S8.M03",
            (payoff.result_sha256,),
            lambda: evaluate_ranking(request.ranking_groups, request.ranking_policy),
            receipts,
        )
        portfolio = self._execute(
            "P9.S8.M04",
            (ranking.result_sha256,),
            lambda: attribute_portfolio_construction(
                request.allocation_records,
                request.virtual_candidate_ledger,
                request.physical_position_ledger,
                request.portfolio_policy,
            ),
            receipts,
        )
        execution = self._execute(
            "P9.S8.M05",
            (
                portfolio.result_sha256,
                request.s7_bundle.payload.reality_gap.result_sha256,
            ),
            lambda: attribute_execution_and_lifecycle(
                request.execution_records,
                request.lifecycle_events,
                request.execution_policy,
            ),
            receipts,
        )
        options = self._execute(
            "P9.S8.M06",
            (execution.result_sha256,),
            lambda: attribute_option_pnl(request.option_intervals, request.option_policy),
            receipts,
        )
        counterfactual = self._execute(
            "P9.S8.M07",
            (
                forecast.result_sha256,
                payoff.result_sha256,
                ranking.result_sha256,
                portfolio.result_sha256,
                execution.result_sha256,
            ),
            lambda: evaluate_counterfactual_policy(
                request.logged_policy_observations,
                request.counterfactual_policy,
            ),
            receipts,
        )
        reconciliation = self._execute(
            "P9.S8.M08",
            tuple(item.result_sha256 for item in (
                forecast,
                payoff,
                ranking,
                portfolio,
                execution,
                options,
                counterfactual,
            )),
            lambda: reconcile_attribution(
                request.factual_pnl,
                forecast,
                payoff,
                ranking,
                portfolio,
                execution,
                options,
                counterfactual,
                request.s7_bundle.payload.rollback_recommendation.state.value,
                request.reconciliation_policy,
            ),
            receipts,
        )
        return self._build_bundle(
            request,
            tuple(receipts),
            forecast,
            payoff,
            ranking,
            portfolio,
            execution,
            options,
            counterfactual,
            reconciliation,
        )

    def _execute(
        self,
        module_id: ModuleIdLiteral,
        input_ids: tuple[str, ...],
        operation: Callable[[], object],
        receipts: list[S8ModuleExecutionReceipt],
    ) -> object:
        started = self._clock()
        result = operation()
        completed = self._clock()
        result_hash = payload_sha256(result)
        quality = getattr(result, "quality", AttributionQuality.QUALIFIED)
        status = _status_for_quality(quality)
        reason_codes = tuple(getattr(result, "reason_codes", ()))
        output_id = f"{module_id}:{result_hash[:16]}"
        diagnostics = {
            "module_id": module_id,
            "result_type": type(result).__name__,
            "result_sha256": result_hash,
            "quality": str(quality),
        }
        provisional = S8ModuleExecutionReceipt(
            module_id=module_id,
            status=status,
            input_artifact_ids=input_ids,
            output_artifact_ids=(output_id,),
            reason_codes=(
                reason_codes
                if status in {ModuleStatus.INVALID, ModuleStatus.FAILED}
                else ()
            ),
            limitations=reason_codes if status in {
                ModuleStatus.LIMITED,
                ModuleStatus.INSUFFICIENT_EVIDENCE,
                ModuleStatus.UNAVAILABLE,
            } else (),
            started_at=started,
            completed_at=completed,
            diagnostics_sha256=payload_sha256(diagnostics),
            integrity=IntegrityEnvelope(payload_sha256="0" * 64),
        )
        digest = payload_sha256(provisional.model_dump(exclude={"integrity"}))
        receipt = provisional.model_copy(
            update={"integrity": IntegrityEnvelope(payload_sha256=digest)}
        )
        receipts.append(receipt)
        return result

    def _build_bundle(
        self,
        request: S8ExecutionRequest,
        receipts: tuple[S8ModuleExecutionReceipt, ...],
        forecast: object,
        payoff: object,
        ranking: object,
        portfolio: object,
        execution: object,
        options: object,
        counterfactual: object,
        reconciliation: object,
    ) -> ProspectiveAttributionBundle:
        subphase_receipt = _subphase_receipt(receipts)
        limitations = tuple(
            sorted(
                {
                    code
                    for receipt in receipts
                    for code in (*receipt.reason_codes, *receipt.limitations)
                }
            )
        )
        payload = ProspectiveAttributionPayload(
            header=request.header,
            upstream_bundle_sha256s=(
                request.upstream.foundation_bundle.content_sha256,
                request.upstream.backtest_metrics_bundle.content_sha256,
                request.upstream.robustness_stress_bundle.content_sha256,
            ),
            s7_bundle_sha256=request.s7_bundle.integrity.payload_sha256,
            forecast_attribution=forecast,  # type: ignore[arg-type]
            payoff_attribution=payoff,  # type: ignore[arg-type]
            ranking_attribution=ranking,  # type: ignore[arg-type]
            portfolio_attribution=portfolio,  # type: ignore[arg-type]
            execution_attribution=execution,  # type: ignore[arg-type]
            option_attribution=options,  # type: ignore[arg-type]
            counterfactual_report=counterfactual,  # type: ignore[arg-type]
            hierarchical_reconciliation=reconciliation,  # type: ignore[arg-type]
            module_receipts=receipts,
            subphase_receipt=subphase_receipt,
            limitations=limitations,
        )
        return ProspectiveAttributionBundle(
            payload=payload,
            integrity=IntegrityEnvelope(payload_sha256=payload_sha256(payload)),
        )


def _status_for_quality(quality: object) -> ModuleStatus:
    if quality is AttributionQuality.INVALID:
        return ModuleStatus.INVALID
    if quality is AttributionQuality.NOT_IDENTIFIABLE:
        return ModuleStatus.UNAVAILABLE
    if quality is AttributionQuality.INSUFFICIENT_EVIDENCE:
        return ModuleStatus.INSUFFICIENT_EVIDENCE
    if quality is AttributionQuality.LIMITED:
        return ModuleStatus.LIMITED
    return ModuleStatus.SUCCESS


def _subphase_receipt(
    receipts: tuple[S8ModuleExecutionReceipt, ...],
) -> S8SubphaseExecutionReceipt:
    statuses = {item.status for item in receipts}
    if ModuleStatus.FAILED in statuses:
        status = ModuleStatus.FAILED
    elif ModuleStatus.INVALID in statuses:
        status = ModuleStatus.INVALID
    elif ModuleStatus.UNAVAILABLE in statuses:
        status = ModuleStatus.UNAVAILABLE
    elif ModuleStatus.INSUFFICIENT_EVIDENCE in statuses:
        status = ModuleStatus.INSUFFICIENT_EVIDENCE
    elif ModuleStatus.LIMITED in statuses:
        status = ModuleStatus.LIMITED
    else:
        status = ModuleStatus.SUCCESS
    outputs = tuple(output for item in receipts for output in item.output_artifact_ids)
    provisional = S8SubphaseExecutionReceipt(
        expected_module_ids=EXPECTED_MODULES,
        module_receipts=receipts,
        status=status,
        output_artifact_ids=outputs,
        integrity=IntegrityEnvelope(payload_sha256="0" * 64),
    )
    digest = payload_sha256(provisional.model_dump(exclude={"integrity"}))
    return provisional.model_copy(
        update={"integrity": IntegrityEnvelope(payload_sha256=digest)}
    )
