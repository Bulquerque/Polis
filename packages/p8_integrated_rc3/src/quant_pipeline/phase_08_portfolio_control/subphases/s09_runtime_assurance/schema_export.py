from __future__ import annotations

import json
from pathlib import Path

from .models_control import RuntimeControlCommand, SafetySupervisorRequest, SafetySupervisorResult
from .models_evidence import RuntimeAssuranceRequest, RuntimeAssuranceResult, RuntimeEvidenceBundle
from .models_invariants import InvariantMonitorRequest, InvariantMonitorResult
from .models_shadow import ShadowEvaluationRequest, ShadowEvaluationResult
from .models_shift import ShiftMonitorRequest, ShiftMonitorResult


SCHEMA_MODELS = {
    "shift_monitor_request": ShiftMonitorRequest,
    "shift_monitor_result": ShiftMonitorResult,
    "invariant_monitor_request": InvariantMonitorRequest,
    "invariant_monitor_result": InvariantMonitorResult,
    "safety_supervisor_request": SafetySupervisorRequest,
    "safety_supervisor_result": SafetySupervisorResult,
    "runtime_control_command": RuntimeControlCommand,
    "shadow_evaluation_request": ShadowEvaluationRequest,
    "shadow_evaluation_result": ShadowEvaluationResult,
    "runtime_evidence_bundle": RuntimeEvidenceBundle,
    "runtime_assurance_request": RuntimeAssuranceRequest,
    "runtime_assurance_result": RuntimeAssuranceResult,
}


def export_schemas(output_dir: Path) -> tuple[Path, ...]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, model in SCHEMA_MODELS.items():
        schema = model.model_json_schema(mode="validation")
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = f"https://inferencia.local/schemas/p8/s9/{name}.schema.json"
        path = output_dir / f"{name}.schema.json"
        path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(path)
    return tuple(written)
