from __future__ import annotations
from .models_common import StrictModel
from .models_handoff import P9EvaluationHandoff, P9HandoffRequest
from .models_qualification import QualificationDecision, RobustnessEvidence, StatisticalEvidence
from .models_audit import IndependentAuditReport
from .models_state import StatefulEvidenceBundle
from .enums import CycleTerminalState

class AuditReleaseRequest(StrictModel):
    stateful_evidence: StatefulEvidenceBundle
    terminal_state: CycleTerminalState
    robustness: RobustnessEvidence
    statistical: StatisticalEvidence
    p9_request_template: P9HandoffRequest

class AuditReleaseResult(StrictModel):
    audit_report: IndependentAuditReport
    qualification: QualificationDecision
    p9_handoff: P9EvaluationHandoff
