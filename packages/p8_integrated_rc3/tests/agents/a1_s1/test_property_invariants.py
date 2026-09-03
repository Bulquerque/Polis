from __future__ import annotations

import json
import random
from decimal import Decimal

from quant_pipeline.phase_08_contracts.canonical import canonical_sha256
from quant_pipeline.phase_08_portfolio_control.s01_boundary.api import run_s1
from quant_pipeline.phase_08_portfolio_control.s01_boundary.modules.m05_current_portfolio_and_account_state_loader import (
    run_module as run_m05,
)
from quant_pipeline.phase_08_portfolio_control.s01_boundary.policies import StateReconciliationPolicy

from tests.agents.a1_s1.factories import full_fixture


def test_canonical_hash_is_mapping_order_invariant() -> None:
    source = {"a": 1, "b": {"x": 2, "y": 3}, "c": [1, 2]}
    for seed in range(25):
        random.seed(seed)
        keys = list(source)
        random.shuffle(keys)
        shuffled = {key: source[key] for key in keys}
        assert canonical_sha256(shuffled) == canonical_sha256(source)


def test_future_unreferenced_artifact_does_not_change_snapshot() -> None:
    fixture_a = full_fixture(ranked=True)
    fixture_b = full_fixture(ranked=True)
    fixture_b.artifact_store._artifacts["future-unreferenced"] = b"future"  # adapter-only perturbation
    a = run_s1(fixture_a.request, fixture_a.ports).snapshot
    b = run_s1(fixture_b.request, fixture_b.ports).snapshot
    assert a.content_sha256 == b.content_sha256


def test_state_tolerance_is_monotonic() -> None:
    fixture = full_fixture(ranked=False, include_external_account=True)
    account = fixture.account_snapshot
    assert account is not None
    from quant_pipeline.phase_08_contracts.state import CashBalance
    from quant_pipeline.phase_08_portfolio_control.s01_boundary.adapters import StaticAccountSnapshotAdapter
    from tests.agents.a1_s1.factories import finalize_hash

    altered = finalize_hash(
        account.model_copy(
            update={
                "cash": (CashBalance(currency="USD", amount=Decimal("100000.02")),),
                "content_sha256": "0" * 64,
            }
        )
    )
    strict = run_m05(
        portfolio_reader=fixture.ports.portfolio_state_reader,
        account_port=StaticAccountSnapshotAdapter(altered),
        context=fixture.request.context,
        policy=StateReconciliationPolicy(cash_tolerance=Decimal("0.01")),
    )
    loose = run_m05(
        portfolio_reader=fixture.ports.portfolio_state_reader,
        account_port=StaticAccountSnapshotAdapter(altered),
        context=fixture.request.context,
        policy=StateReconciliationPolicy(cash_tolerance=Decimal("0.05")),
    )
    assert len(loose.current_state.quality_report.discrepancies) <= len(
        strict.current_state.quality_report.discrepancies
    )


def test_no_action_hash_is_stable_across_json_whitespace() -> None:
    fixture = full_fixture(ranked=False)
    instance = json.loads(fixture.request.p7_handoff_bytes)
    compact = json.dumps(instance, separators=(",", ":")).encode()
    pretty = json.dumps(instance, indent=4).encode()
    request_a = fixture.request.__class__(
        p7_handoff_bytes=compact,
        feedback_refs=fixture.request.feedback_refs,
        market_snapshot_ref=fixture.request.market_snapshot_ref,
        context=fixture.request.context,
    )
    request_b = fixture.request.__class__(
        p7_handoff_bytes=pretty,
        feedback_refs=fixture.request.feedback_refs,
        market_snapshot_ref=fixture.request.market_snapshot_ref,
        context=fixture.request.context,
    )
    a = run_s1(request_a, fixture.ports).snapshot
    fixture2 = full_fixture(ranked=False)
    request_b = request_b.__class__(
        p7_handoff_bytes=pretty,
        feedback_refs=fixture2.request.feedback_refs,
        market_snapshot_ref=fixture2.request.market_snapshot_ref,
        context=fixture2.request.context,
    )
    b = run_s1(request_b, fixture2.ports).snapshot
    assert a.content_sha256 == b.content_sha256
