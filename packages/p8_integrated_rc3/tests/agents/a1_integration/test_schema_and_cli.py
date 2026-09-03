from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

from quant_pipeline.phase_08_portfolio_control.agent1_integration.cli import main
from quant_pipeline.phase_08_portfolio_control.agent1_integration.schema_export import export_schema


def test_exported_schema_is_draft_2020_12(tmp_path: Path) -> None:
    path = export_schema(tmp_path)
    schema = json.loads(path.read_text())
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(schema)


def test_cli_info(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["p8-agent1", "info"])
    assert main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["components"] == {"S1": "0.1.0", "S2": "0.1.0"}


def test_cli_generate_schema(monkeypatch, capsys, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "argv", ["p8-agent1", "generate-schema", str(tmp_path)])
    assert main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert Path(payload["written"]).exists()


def test_cli_validate_receipt(monkeypatch, capsys, tmp_path: Path) -> None:
    from datetime import timedelta
    from quant_pipeline.phase_08_portfolio_control.agent1_integration.api import Agent1Ports, Agent1RunRequest, run_agent1
    from tests.agents.a1_integration.support.s1_factory import full_fixture

    fixture = full_fixture(ranked=True)
    result = run_agent1(
        Agent1RunRequest(fixture.request, fixture.request.context.computed_at + timedelta(seconds=1)),
        Agent1Ports(s1=fixture.ports),
    )
    path = tmp_path / "receipt.json"
    path.write_text(result.receipt.model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["p8-agent1", "validate-receipt", str(path)])
    assert main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"status": "PASS", "content_sha256": result.receipt.content_sha256}
