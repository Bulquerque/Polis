from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FORBIDDEN = {"rank", "top_k", "recommended_trade", "ltr_score", "portfolio_weight", "execution_order"}


def _walk(value):
    if isinstance(value, dict):
        yield from value.keys()
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def test_output_fixture_contains_no_downstream_decision_fields():
    fixture = json.loads((ROOT / "fixtures/s3/minimal_output_fixture.json").read_text(encoding="utf-8"))
    assert FORBIDDEN.isdisjoint(set(_walk(fixture)))
