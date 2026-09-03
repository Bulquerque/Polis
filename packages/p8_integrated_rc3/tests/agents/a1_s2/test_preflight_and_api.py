
from datetime import timedelta

import pytest

from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.adapters import InMemoryDebugBundleWriter
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.api import S2Ports, S2RunRequest, run_s2
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.context import S2ExecutionContext
from quant_pipeline.phase_08_portfolio_control.s02_candidate_context.errors import InputBundleIntegrityError
from tests.agents.a1_s2.factories import build_input


def test_ranked_pipeline_runs_end_to_end():
    bundle,context=build_input()
    result=run_s2(S2RunRequest(input_bundle=bundle,context=context))
    assert result.bundle.static_action_universe.forwarded_candidate_ids == ("cand-1",)
    assert result.bundle.snapshot_hash == bundle.snapshot.content_sha256


def test_no_action_empty_ranked_pipeline():
    from quant_pipeline.phase_08_contracts.enums import P7TerminalState
    bundle,context=build_input(specs=(),terminal_candidates=(("cand-x",P7TerminalState.ABSTAINED),))
    result=run_s2(S2RunRequest(bundle,context))
    assert result.bundle.normalized_intents.candidates == ()
    assert result.bundle.static_action_universe.forwarded_candidate_ids == ()


def test_tampered_bundle_hash_is_fatal_and_debugged():
    bundle,context=build_input()
    tampered=bundle.model_copy(update={"content_sha256":"0"*64})
    writer=InMemoryDebugBundleWriter()
    with pytest.raises(InputBundleIntegrityError):
        run_s2(S2RunRequest(tampered,context),ports=S2Ports(debug_writer=writer))
    assert writer.failures[0].module_id=="P8.S2.PREFLIGHT"


def test_component_hash_mismatch_is_fatal():
    bundle,context=build_input()
    snapshot=bundle.snapshot.model_copy(update={"candidate_ledger_hash":"0"*64})
    from quant_pipeline.phase_08_contracts.canonical import finalize_content_hash
    snapshot=finalize_content_hash(snapshot)
    broken=bundle.model_copy(update={"snapshot":snapshot,"content_sha256":"0"*64})
    broken=finalize_content_hash(broken)
    with pytest.raises(InputBundleIntegrityError,match="candidate_ledger_hash"):
        run_s2(S2RunRequest(broken,context))


def test_context_mismatch_is_fatal():
    bundle,context=build_input()
    wrong=S2ExecutionContext(run_id="other",cycle_id=context.cycle_id,decision_time=context.decision_time,computed_at=context.computed_at)
    with pytest.raises(InputBundleIntegrityError):
        run_s2(S2RunRequest(bundle,wrong))


def test_context_requires_aware_and_ordered_times():
    from datetime import datetime
    with pytest.raises(ValueError):
        S2ExecutionContext(run_id="r",cycle_id="c",decision_time=datetime(2026,1,1),computed_at=datetime(2026,1,1))
    bundle,context=build_input()
    with pytest.raises(ValueError):
        S2ExecutionContext(run_id="r",cycle_id="c",decision_time=context.decision_time,computed_at=context.decision_time-timedelta(seconds=1))
