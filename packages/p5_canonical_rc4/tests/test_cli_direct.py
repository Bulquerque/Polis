from __future__ import annotations

from importlib.metadata import PackageNotFoundError

import json

from quant_pipeline.phase_05_underlying_forecasts import cli


def test_doctor_cli_direct(capsys):
    assert cli.main(["doctor"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "PASS"
    assert payload["module_count"] == 45
    assert payload["subphase_count"] == 9


def test_list_modules_cli_direct(capsys):
    assert cli.main(["list-modules"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 45
    assert lines[0].startswith("P5.S1.M01")
    assert lines[-1].startswith("P5.S9.M05")


def test_doctor_source_checkout_fallback(monkeypatch, capsys):
    def fail(_name):
        raise PackageNotFoundError("not installed")

    monkeypatch.setattr(cli, "version", fail)
    assert cli.main(["doctor"]) == 0
    assert json.loads(capsys.readouterr().out)["package_version"] == "source-checkout"
