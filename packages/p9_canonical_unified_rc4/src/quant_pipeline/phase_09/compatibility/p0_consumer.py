from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .errors import ContractMismatchError, PhaseUnavailableError
from .p0_reporting import P0ControlPlaneReportSet


def validate_p0_control_plane_consumer(
    *,
    reports: P0ControlPlaneReportSet,
    p0_source_root: str | Path,
) -> dict[str, Any]:
    """Run the qualified P0 normalizers against the P9 report payloads."""

    root = Path(p0_source_root).resolve()
    source = root / "src"
    if not source.is_dir():
        raise PhaseUnavailableError(f"P0 source root is invalid: {root}")
    script = r'''
import json, os, sys
sys.path.insert(0, os.environ["P0_SOURCE"])
from quant_pipeline.phase_00_zero_trust_guardian.modules._p0_s4_reports import normalize_family
from quant_pipeline.phase_00_zero_trust_guardian.modules._p0_s6_core import source_control, validate
p=json.load(sys.stdin)
normalized=normalize_family(
    {"reports": [p["test_run_report"]]},
    "test_run_report_all_phases",
    {"skipped_test_policy": "partial"},
)
dashboard=source_control(p["dashboard_phase_payload"], "dashboard_phase_payload")
validate(dashboard, "dashboard_phase_payload.schema.yaml", "dashboard_phase_payload")
print(json.dumps({"test_run_report": normalized[0], "dashboard_phase_payload": dashboard}))
'''
    env = dict(os.environ)
    env["P0_SOURCE"] = str(source)
    process = subprocess.run(
        [sys.executable, "-I", "-c", script],
        input=json.dumps(reports.model_dump(mode="json"), ensure_ascii=False),
        text=True,
        capture_output=True,
        env=env,
        timeout=60,
        check=False,
    )
    if process.returncode != 0:
        detail = process.stderr.strip() or process.stdout.strip()
        raise ContractMismatchError(f"P0 rejected control-plane reports: {detail}")
    result = json.loads(process.stdout)
    if result["test_run_report"]["phase_id"] != "P9":
        raise ContractMismatchError("P0 normalized the wrong phase report")
    return result
