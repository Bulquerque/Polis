from __future__ import annotations

from quant_pipeline.phase_07_strategy_tournament.tournament.s4_runner import run_subphase

from tests.tournament.tests.s4.factories import execution_config, make_bundle

FORBIDDEN = {"future_return", "realized_return", "realized_pnl", "outcome", "target_return", "rank", "portfolio_weight", "execution_price", "fill_price"}


def _walk(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def test_outputs_do_not_contain_forbidden_fields():
    outputs = run_subphase(make_bundle(), execution_config())["outputs"]
    assert not (set(_walk(outputs)) & FORBIDDEN)
