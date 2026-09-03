from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .errors import ContractMismatchError, PhaseUnavailableError


_PHASES = {
    "P5": (
        "phase_05_underlying_forecasts_agent_package_RC4_1",
        "quant_pipeline.phase_05_underlying_forecasts.modules.P5_S1_M02_optional_signal_feedback_loader",
        "signal_feedback_report",
    ),
    "P7": (
        "phase_07_ranking_agent_package_RC4_1",
        "quant_pipeline.phase_07_ranking.modules.P7_S1_M02_optional_ranking_feedback_loader",
        "ranking_feedback_report",
    ),
    "P8": (
        "phase_08_portfolio_backtest_agent_package_RC4_1",
        "quant_pipeline.phase_08_portfolio_backtest.modules.P8_S1_M02_optional_portfolio_feedback_loader",
        "portfolio_feedback_report",
    ),
}


def validate_legacy_feedback_consumer(
    *,
    phase_id: str,
    feedback_record: dict[str, Any],
    phase_package_root: str | Path,
) -> dict[str, Any]:
    if phase_id not in _PHASES:
        raise ValueError(f"unsupported legacy feedback consumer: {phase_id}")
    _, module_name, input_name = _PHASES[phase_id]
    root = Path(phase_package_root).resolve()
    source = root / "src"
    if not source.is_dir():
        raise PhaseUnavailableError(f"legacy phase source root is invalid: {root}")
    script = f'''
import json, os, sys
sys.path.insert(0, os.environ["PHASE_SOURCE"])
from {module_name} import run_module
payload=json.load(sys.stdin)
envelope={{
    "artifact_id": "{input_name}-" + payload["feedback_id"],
    "created_at": payload["created_at"],
    "lineage_id": "lineage-" + payload["feedback_id"],
    "pipeline_version": "V14.1-RC4.1",
    "records": [payload],
}}
result=run_module({{"{input_name}": envelope}}, {{
    "created_at": "2026-08-04T10:00:00Z", "pipeline_version": "V14.1-RC4.1"
}})
print(json.dumps(result, default=str))
'''
    env = dict(os.environ)
    env["PHASE_SOURCE"] = str(source)
    process = subprocess.run(
        [sys.executable, "-I", "-c", script],
        input=json.dumps(feedback_record, ensure_ascii=False),
        text=True,
        capture_output=True,
        env=env,
        timeout=60,
        check=False,
    )
    if process.returncode != 0:
        detail = process.stderr.strip() or process.stdout.strip()
        raise ContractMismatchError(f"{phase_id} legacy feedback consumer rejected payload: {detail}")
    result = json.loads(process.stdout)
    if result.get("module_id") not in {"P5.S1.M02", "P7.S1.M02", "P8.S1.M02"}:
        raise ContractMismatchError(f"unexpected {phase_id} consumer receipt")
    return result
