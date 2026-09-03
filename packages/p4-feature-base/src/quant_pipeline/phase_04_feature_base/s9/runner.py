from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import TypeAdapter

from ..modules.P4_S9_M01_feature_lineage_temporal_safety_auditor import run_module as m01
from ..modules.P4_S9_M02_drift_coverage_quality_gate import run_module as m02
from ..modules.P4_S9_M03_model_consumer_view_packager import run_module as m03
from ..modules.P4_S9_M04_phase5_feature_handoff_builder import run_module as m04
from ..modules.P4_S9_M05_phase5_consumer_receipt_validator import run_module as m05
from ..modules.P4_S9_M06_research_attempt_ledger_manager import run_module as m06
from .artifacts import ArtifactEnvelope, ExecutionContext

MODULE_SEQUENCE = (m01, m02, m03, m06, m04, m05)
OUTPUTS = {
    "feature_lineage_report",
    "temporal_safety_report",
    "drift_safety_report",
    "p4_quality_gate_decision",
    "model_consumer_view_manifest",
    "model_consumer_view_bundle",
    "phase5_feature_handoff_manifest",
    "p4_to_p5_integration_receipt",
    "research_attempt_ledger",
    "rejected_feature_graveyard",
    "research_budget_compliance_report",
}


def run_subphase(
    inputs: dict[str, ArtifactEnvelope], context: ExecutionContext
) -> dict[str, ArtifactEnvelope]:
    artifacts = dict(inputs)
    for module in MODULE_SEQUENCE:
        artifacts.update(module(artifacts, context))
    return {name: artifacts[name] for name in sorted(OUTPUTS)}


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python -m quant_pipeline.phase_04_feature_base.s9.runner INPUT.json")
        return 2
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    context = ExecutionContext.model_validate(payload["context"])
    inputs = TypeAdapter(dict[str, ArtifactEnvelope]).validate_python(payload["inputs"])
    outputs = run_subphase(inputs, context)
    print(json.dumps({name: value.model_dump(mode="json") for name, value in outputs.items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
