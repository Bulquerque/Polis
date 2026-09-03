
"""Thin deterministic orchestration for the six S2 modules."""

from __future__ import annotations

from quant_pipeline.phase_08_contracts.canonical import canonical_sha256

from .api import S2Ports, S2RunRequest, S2RunResult
from .contracts.bundle import P8CandidateContextBundleV1
from .contracts.results import S2OutputResult
from .debug import S2FailureDebugBundle
from .errors import P8S2Error, InputBundleIntegrityError
from .module_support import build_receipt, seal, validate_s2_input_bundle
from .modules import run_m01, run_m02, run_m03, run_m04, run_m05, run_m06
from .policies import S2Policy


def _write_failure(module_id: str, error: P8S2Error, request: S2RunRequest, ports: S2Ports) -> None:
    if ports.debug_writer is None:
        return
    ports.debug_writer.write_failure(S2FailureDebugBundle(
        module_id=module_id,
        error_type=type(error).__name__,
        reason_code=error.reason_code,
        message=str(error),
        run_id=request.context.run_id,
        cycle_id=request.context.cycle_id,
        decision_time=request.context.decision_time,
        computed_at=request.context.computed_at,
        input_hashes=(request.input_bundle.content_sha256,),
    ))


def run_s2_pipeline(*, request: S2RunRequest, ports: S2Ports, policy: S2Policy) -> S2RunResult:
    module_id = "P8.S2.PREFLIGHT"
    try:
        validate_s2_input_bundle(request.input_bundle)
        snapshot = request.input_bundle.snapshot
        if request.context.run_id != snapshot.run_id or request.context.cycle_id != snapshot.cycle_id:
            raise InputBundleIntegrityError("S2 context run/cycle differs from snapshot")
        if request.context.decision_time != snapshot.decision_time:
            raise InputBundleIntegrityError("S2 context decision_time differs from snapshot")
        module_id = "P8.S2.M01"
        m01 = run_m01(request.input_bundle, context=request.context)
        module_id = "P8.S2.M02"
        m02 = run_m02(request.input_bundle, m01, context=request.context)
        module_id = "P8.S2.M03"
        m03 = run_m03(request.input_bundle, m01, m02, context=request.context, policy=policy.equivalence)
        module_id = "P8.S2.M04"
        m04 = run_m04(request.input_bundle, m01, context=request.context)
        module_id = "P8.S2.M05"
        m05 = run_m05(request.input_bundle, m01, m03, context=request.context, policy=policy.static_admission)
        module_id = "P8.S2.M06"
        m06 = run_m06(request.input_bundle, m05, context=request.context, policy=policy.ordinal)
        module_id = "P8.S2.OUTPUT"
        output_bundle = seal(P8CandidateContextBundleV1(
            contract_version="P8_CANDIDATE_CONTEXT_BUNDLE_V1",
            schema_version="1.0.0",
            snapshot_id=snapshot.snapshot_id,
            snapshot_hash=snapshot.content_sha256,
            normalized_intents=m01.normalized_intents,
            exposure_graph=m02.exposure_graph,
            equivalence_groups=m03.equivalence_groups,
            soft_similarity_requests=m03.soft_similarity_requests,
            netting_transform=m04.netting_transform,
            static_action_universe=m05.static_action_universe,
            ordinal_preferences=m06.ordinal_preferences,
            content_sha256="0" * 64,
        ))
        output_receipt = build_receipt(
            module_id=module_id,
            inputs=(m01.normalized_intents, m02.exposure_graph, m03.equivalence_groups,
                    m03.soft_similarity_requests, m04.netting_transform, m05.static_action_universe,
                    m06.ordinal_preferences),
            output=output_bundle,
            computed_at=request.context.computed_at,
        )
        output = S2OutputResult(bundle=output_bundle, receipt=output_receipt)
    except P8S2Error as error:
        _write_failure(module_id, error, request, ports)
        raise
    return S2RunResult(m01=m01, m02=m02, m03=m03, m04=m04, m05=m05, m06=m06, output=output)
