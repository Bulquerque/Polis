from __future__ import annotations
import json
from pathlib import Path
from pydantic import BaseModel
from .models_audit import IndependentAuditReport
from .models_handoff import P9EvaluationHandoff, P9HandoffRequest
from .models_orchestration import AuditReleaseRequest, AuditReleaseResult
from .models_qualification import QualificationDecision, QualificationRequest
from .models_release import ReleasePublicationRequest, ReleasePublicationResult
from .models_state import StatefulEvidenceBundle

SCHEMAS: dict[str, type[BaseModel]] = {
    "stateful_evidence_bundle": StatefulEvidenceBundle,
    "independent_audit_report": IndependentAuditReport,
    "qualification_request": QualificationRequest,
    "qualification_decision": QualificationDecision,
    "p9_handoff_request": P9HandoffRequest,
    "p9_evaluation_handoff": P9EvaluationHandoff,
    "release_publication_request": ReleasePublicationRequest,
    "release_publication_result": ReleasePublicationResult,
    "audit_release_request": AuditReleaseRequest,
    "audit_release_result": AuditReleaseResult,
}

def export_schemas(output_dir: str | Path) -> tuple[Path, ...]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    written = []
    for name, model in SCHEMAS.items():
        schema = model.model_json_schema(mode="validation")
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        path = target/f"{name}.schema.json"
        path.write_text(json.dumps(schema, indent=2, sort_keys=True)+"\n", encoding="utf-8")
        written.append(path)
    return tuple(written)
