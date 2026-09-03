from __future__ import annotations

from datetime import datetime

from .contracts import ModuleReceipt, S5State, content_sha256
from .m01_dependence_and_sampling_diagnostics import diagnose_dependence
from .m02_automatic_block_length_selector import select_block_length
from .m03_time_series_block_bootstrap_engine import generate_bootstrap_indices
from .m04_hierarchical_portfolio_bootstrap_engine import evaluate_hierarchical_bootstrap
from .m05_trade_and_execution_resampling_engine import resample_trade_episodes
from .m06_bootstrap_metric_distribution_builder import build_metric_distributions
from .m07_sharpe_inference_and_deflation_engine import infer_sharpe
from .m08_backtest_overfitting_multiple_testing_qualification_gate import qualify_backtest
from .metric_registry import MetricCalculatorRegistry
from .models import (
    BlockBootstrapRequest,
    BlockLengthSelectionRequest,
    HierarchicalBootstrapRequest,
    MetricDistributionRequest,
    RobustnessQualificationRequest,
    S5OutputBundle,
    S5RunRequest,
    SharpeInferenceRequest,
    TradeResamplingRequest,
)


class S5PipelineError(RuntimeError):
    """Raised when a hard prerequisite blocks the integrated S5 runner."""


def _receipt(module_id: str, output: object, status: S5State, at: datetime) -> ModuleReceipt:
    reason_codes = tuple(getattr(output, "reason_codes", ()))
    limitations = tuple(getattr(output, "limitations", ()))
    return ModuleReceipt(
        module_id=module_id,
        status=status,
        reason_codes=reason_codes,
        limitations=limitations,
        output_sha256=content_sha256(output),
        started_at=at,
        completed_at=at,
    )


def run_s5(
    request: S5RunRequest,
    metric_registry: MetricCalculatorRegistry | None = None,
) -> S5OutputBundle:
    """Execute P9.S5 while preserving module boundaries and receipts."""

    context = request.dependence.context
    at = context.decision_time
    receipts: list[ModuleReceipt] = []

    dependence = diagnose_dependence(request.dependence)
    receipts.append(_receipt("P9.S5.M01", dependence, dependence.status, at))
    if dependence.status in {S5State.INVALID_INPUT, S5State.IRREGULAR_TIME_UNSUPPORTED}:
        raise S5PipelineError(f"M01 blocked S5: {dependence.status}")

    block_lengths = select_block_length(
        BlockLengthSelectionRequest(
            context=context,
            series=request.dependence.series,
            diagnostics=dependence,
            policy=request.block_length_policy,
        )
    )
    receipts.append(_receipt("P9.S5.M02", block_lengths, block_lengths.status, at))
    if request.bootstrap_policy.method.value == "MOVING":
        selected_block = block_lengths.joint_moving_block_length
    elif request.bootstrap_policy.method.value == "CIRCULAR":
        selected_block = block_lengths.joint_circular_block_length
    else:
        selected_block = block_lengths.joint_stationary_block_length

    bootstrap = generate_bootstrap_indices(
        BlockBootstrapRequest(
            context=context,
            observation_count=len(request.dependence.series.timestamps),
            block_length=selected_block,
            seed_policy=request.seed_policy,
            policy=request.bootstrap_policy,
        )
    )
    receipts.append(_receipt("P9.S5.M03", bootstrap, bootstrap.status, at))
    if bootstrap.manifest is None:
        raise S5PipelineError(f"M03 blocked S5: {bootstrap.reason_codes}")

    hierarchical = evaluate_hierarchical_bootstrap(
        HierarchicalBootstrapRequest(
            context=context,
            series=request.dependence.series,
            indices=bootstrap.manifest,
            policy=request.hierarchical_policy,
        )
    )
    receipts.append(_receipt("P9.S5.M04", hierarchical, hierarchical.status, at))

    trade_resampling = None
    if request.dependence.trades is not None:
        trade_resampling = resample_trade_episodes(
            TradeResamplingRequest(
                context=context,
                trades=request.dependence.trades,
                seed_policy=request.seed_policy,
                policy=request.trade_policy,
            )
        )
        receipts.append(
            _receipt("P9.S5.M05", trade_resampling, trade_resampling.status, at)
        )
    else:
        receipts.append(
            ModuleReceipt(
                module_id="P9.S5.M05",
                status=S5State.INSUFFICIENT_EVIDENCE,
                reason_codes=("P9_BOOTSTRAP_OVERLAP_METADATA_MISSING",),
                limitations=("trade resampling was not executed",),
                output_sha256=content_sha256(None),
                started_at=at,
                completed_at=at,
            )
        )

    metric_distributions = build_metric_distributions(
        MetricDistributionRequest(
            context=context,
            series=request.dependence.series,
            indices=bootstrap.manifest,
            metric_definitions=request.metric_definitions,
            policy=request.metric_policy,
        ),
        registry=metric_registry,
    )
    receipts.append(
        _receipt("P9.S5.M06", metric_distributions, metric_distributions.status, at)
    )

    sharpe_inference = infer_sharpe(
        SharpeInferenceRequest(
            context=context,
            series=request.dependence.series,
            target_series_id=request.sharpe_target_series_id,
            target_configuration_id=context.configuration_id,
            trial_performance=request.trial_performance,
            metric_distributions=metric_distributions,
            policy=request.sharpe_policy,
        )
    )
    receipts.append(
        _receipt("P9.S5.M07", sharpe_inference, sharpe_inference.status, at)
    )

    qualification = qualify_backtest(
        RobustnessQualificationRequest(
            context=context,
            target_configuration_id=context.configuration_id,
            target_metric_id=request.target_metric_id,
            trial_performance=request.trial_performance,
            fold_scores=request.fold_scores,
            metric_distributions=metric_distributions,
            sharpe_inference=sharpe_inference,
            seed_policy=request.seed_policy,
            multiple_testing_policy=request.multiple_testing_policy,
            threshold_policy=request.qualification_policy,
        )
    )
    receipts.append(_receipt("P9.S5.M08", qualification, qualification.status, at))

    payload = {
        "context": context.model_dump(mode="json"),
        "upstream_metrics": (
            None
            if request.upstream_metrics is None
            else request.upstream_metrics.model_dump(mode="json")
        ),
        "dependence_sha256": content_sha256(dependence),
        "block_lengths_sha256": content_sha256(block_lengths),
        "bootstrap_sha256": content_sha256(bootstrap),
        "hierarchical_sha256": content_sha256(hierarchical),
        "trade_resampling_sha256": content_sha256(trade_resampling),
        "metric_distributions_sha256": content_sha256(metric_distributions),
        "sharpe_inference_sha256": content_sha256(sharpe_inference),
        "qualification_sha256": content_sha256(qualification),
        "receipt_sha256": [content_sha256(receipt) for receipt in receipts],
    }
    bundle_hash = content_sha256(payload)
    return S5OutputBundle(
        bundle_id=f"{context.run_id}:P9.S5:{bundle_hash[:16]}",
        context=context,
        upstream_metrics=request.upstream_metrics,
        dependence=dependence,
        block_lengths=block_lengths,
        bootstrap=bootstrap,
        hierarchical=hierarchical,
        trade_resampling=trade_resampling,
        metric_distributions=metric_distributions,
        sharpe_inference=sharpe_inference,
        qualification=qualification,
        module_receipts=tuple(receipts),
        bundle_sha256=bundle_hash,
    )
