from __future__ import annotations

from quant_pipeline.phase_03_agents_rag_memory.s27.entrypoints import run_m01, run_m02, run_m03
from s27_test_support import m01_inputs, m02_inputs, m03_inputs


def test_complete_s27_handoff_has_consistent_grain_and_context() -> None:
    belief = run_m01(m01_inputs())["belief_distribution_panel"]
    attention = run_m02(m02_inputs())["attention_information_metrics"]
    cascade = run_m03(m03_inputs())["cascade_metrics_panel"]
    for artifact in (belief, attention, cascade):
        assert artifact["run_id"] == "run-s27-001"
        assert artifact["cycle_id"] == 7
        assert artifact["as_of_time"] == "2026-06-10T00:00:00Z"
        assert artifact["formula_version"] == "p3.s27.formulas.v1"
    grain = ("PETR4", "directional_outlook", "5d")
    assert tuple(belief["records"][0][key] for key in ("underlying_id", "proposition_id", "horizon")) == grain
    assert tuple(attention["records"][0][key] for key in ("underlying_id", "proposition_id", "horizon")) == grain
    assert tuple(cascade["records"][0][key] for key in ("underlying_id", "proposition_id", "horizon")) == grain


def test_outputs_do_not_expose_forbidden_authority() -> None:
    forbidden = {"future_return", "candidate_score", "rank_score", "portfolio_weight", "trade_decision", "buy_sell_signal"}
    outputs = [run_m01(m01_inputs()), run_m02(m02_inputs()), run_m03(m03_inputs())]
    text = str(outputs)
    assert all(field not in text for field in forbidden)
