from pathlib import Path
import sys

from quant_pipeline.phase_09.subphases.s06_structural_stress.cli import main
from quant_pipeline.phase_09.subphases.s06_structural_stress.models import S6OutputBundle


def test_cli_main_run_and_schema(full_request, tmp_path: Path, monkeypatch):
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "output.json"
    request_path.write_text(full_request.model_dump_json(indent=2), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["p9-s6", "run", str(request_path), str(output_path)])
    assert main() == 0
    S6OutputBundle.model_validate_json(output_path.read_text(encoding="utf-8"))
    schema_dir = tmp_path / "schemas"
    monkeypatch.setattr(sys, "argv", ["p9-s6", "schemas", str(schema_dir)])
    assert main() == 0
    assert list(schema_dir.glob("*.json"))
