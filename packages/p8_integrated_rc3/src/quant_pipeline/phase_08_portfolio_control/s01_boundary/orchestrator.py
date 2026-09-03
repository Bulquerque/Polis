"""Thin, deterministic orchestration for the six S1 modules."""

from __future__ import annotations

from quant_pipeline.phase_08_contracts.canonical import canonical_sha256, raw_sha256

from .api import S1Ports, S1RunRequest, S1RunResult
from .debug import S1FailureDebugBundle
from .errors import P8S1Error
from .modules import run_m01, run_m02, run_m03, run_m04, run_m05, run_m06
from .policies import S1Policy


def _write_failure(
    *,
    module_id: str,
    error: P8S1Error,
    request: S1RunRequest,
    ports: S1Ports,
) -> None:
    if ports.debug_writer is None:
        return
    hashes = [raw_sha256(request.p7_handoff_bytes), request.market_snapshot_ref.content_sha256]
    hashes.extend(reference.content_sha256 for reference in request.feedback_refs)
    bundle = S1FailureDebugBundle(
        module_id=module_id,
        error_type=type(error).__name__,
        reason_code=error.reason_code,
        message=str(error),
        run_id=request.context.run_id,
        cycle_id=request.context.cycle_id,
        cycle_sequence=request.context.cycle_sequence,
        decision_time=request.context.decision_time,
        market_cutoff_at=request.context.market_cutoff_at,
        computed_at=request.context.computed_at,
        runtime_mode=request.context.runtime_mode,
        input_hashes=tuple(hashes),
    )
    ports.debug_writer.write_failure(bundle)


def run_s1_pipeline(*, request: S1RunRequest, ports: S1Ports, policy: S1Policy) -> S1RunResult:
    module_id = "P8.S1.M01"
    try:
        m01 = run_m01(request.p7_handoff_bytes, context=request.context, policy=policy.compatibility)
        module_id = "P8.S1.M02"
        m02 = run_m02(m01.bundle, context=request.context)
        module_id = "P8.S1.M03"
        m03 = run_m03(
            m01.bundle,
            m02.ledger,
            store=ports.artifact_store,
            context=request.context,
            policy=policy.reference_resolution,
        )
        module_id = "P8.S1.M04"
        m04 = run_m04(
            request.feedback_refs,
            store=ports.artifact_store,
            idempotency_store=ports.idempotency_store,
            context=request.context,
        )
        module_id = "P8.S1.M05"
        m05 = run_m05(
            portfolio_reader=ports.portfolio_state_reader,
            account_port=ports.account_snapshot_port,
            context=request.context,
            policy=policy.state_reconciliation,
        )
        module_id = "P8.S1.M06"
        m06 = run_m06(
            m01,
            m02,
            m03,
            m04,
            m05,
            market_snapshot_ref=request.market_snapshot_ref,
            store=ports.artifact_store,
            context=request.context,
        )
    except P8S1Error as error:
        _write_failure(module_id=module_id, error=error, request=request, ports=ports)
        raise
    return S1RunResult(m01=m01, m02=m02, m03=m03, m04=m04, m05=m05, m06=m06)
