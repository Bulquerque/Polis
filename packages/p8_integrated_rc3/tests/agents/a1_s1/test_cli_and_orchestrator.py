from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from quant_pipeline.phase_08_portfolio_control.s01_boundary.adapters.debug_filesystem import (
    FileDebugBundleWriter,
)
from quant_pipeline.phase_08_portfolio_control.s01_boundary.api import S1Ports, run_s1
from quant_pipeline.phase_08_portfolio_control.s01_boundary.cli import main
from quant_pipeline.phase_08_portfolio_control.s01_boundary.errors import HashMismatchError

from tests.agents.a1_s1.factories import full_fixture


def test_cli_generates_schemas(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "schemas"
    monkeypatch.setattr(sys, "argv", ["p8-s1", "generate-schemas", str(target)])
    assert main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["written"]
    assert all(Path(path).exists() for path in output["written"])


def test_cli_validates_real_handoff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    fixture = full_fixture(ranked=False)
    path = tmp_path / "handoff.json"
    path.write_bytes(fixture.request.p7_handoff_bytes)
    context = fixture.request.context
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "p8-s1",
            "validate-handoff",
            str(path),
            "--run-id",
            context.run_id,
            "--cycle-id",
            context.cycle_id,
            "--cycle-sequence",
            str(context.cycle_sequence),
            "--decision-time",
            context.decision_time.isoformat(),
            "--market-cutoff-at",
            context.market_cutoff_at.isoformat(),
            "--computed-at",
            context.computed_at.isoformat(),
            "--runtime-mode",
            context.runtime_mode.value,
        ],
    )
    assert main() == 0
    assert '"module_id": "P8.S1.M01"' in capsys.readouterr().out


def test_orchestrator_writes_debug_bundle_at_failing_module(tmp_path: Path) -> None:
    fixture = full_fixture(ranked=False)
    tampered = fixture.request.p7_handoff_bytes.replace(b"cycle-010", b"cycle-011")
    request = fixture.request.__class__(
        p7_handoff_bytes=tampered,
        feedback_refs=fixture.request.feedback_refs,
        market_snapshot_ref=fixture.request.market_snapshot_ref,
        context=fixture.request.context,
    )
    ports = S1Ports(
        artifact_store=fixture.ports.artifact_store,
        idempotency_store=fixture.ports.idempotency_store,
        portfolio_state_reader=fixture.ports.portfolio_state_reader,
        account_snapshot_port=fixture.ports.account_snapshot_port,
        debug_writer=FileDebugBundleWriter(tmp_path),
    )
    with pytest.raises(HashMismatchError):
        run_s1(request, ports)
    files = list(tmp_path.glob("P8_S1_M01_*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text())
    assert payload["module_id"] == "P8.S1.M01"
    assert payload["reason_code"] == "HASH_MISMATCH"
