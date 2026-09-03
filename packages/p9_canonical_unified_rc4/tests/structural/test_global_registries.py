from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_global_token_and_contract_registries_are_complete() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/validate_p9_registries.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_global_reason_registry_is_unique() -> None:
    payload = json.loads((ROOT / "registries/p9_reason_code_registry.json").read_text())
    codes = payload["reason_codes"]
    assert codes
    assert len(codes) == len(set(codes))
