"""P7.S7.M03 — apply final material safety rules."""
from __future__ import annotations

from collections import Counter
from typing import Mapping

from ..application.module_io import parse_envelope, parse_records
from ..application.reconciliation import load_scoring_bundle
from ..application.runtime import Timer, artifact_from_records, receipt
from ..boundary.config import S7Config
from ..boundary.outputs import AuditRecord, BlockedRecord, DecisionRecord, DiversityAdjustedScoreRecord
from ..errors import ErrorContext, IntegrityViolation
from ..subphases.s7_safety_diversity.safety import evaluate_safety

MODULE_ID = "P7.S7.M03"


def run_module(inputs: Mapping[str, object], config: Mapping[str, object]) -> dict[str, object]:
    timer = Timer()
    cfg = S7Config.model_validate(config)
    bundle = load_scoring_bundle(inputs, MODULE_ID, cfg.forbidden_fields)
    score_envelope = parse_envelope(inputs, "diversity_adjusted_score_panel", MODULE_ID)
    score_records = parse_records(score_envelope, DiversityAdjustedScoreRecord, MODULE_ID)
    score_map = {record.candidate_id: record for record in score_records}
    candidate_ids = {candidate.candidate_id for candidate in bundle.candidates}
    if set(score_map) != candidate_ids or len(score_map) != len(score_records):
        context = ErrorContext(MODULE_ID, candidate_ids=tuple(sorted(candidate_ids ^ set(score_map))))
        raise IntegrityViolation("P7_SCORE_CANDIDATE_SET_MISMATCH", "score/candidate sets differ", context)
    eligible: list[DecisionRecord] = []
    blocked: list[BlockedRecord] = []
    reasons: list[str] = []
    for candidate in bundle.candidates:
        upstream = bundle.preblocks.get(candidate.candidate_id)
        upstream_reasons = upstream.reason_codes if upstream else ()
        outcome = evaluate_safety(candidate, score_map[candidate.candidate_id].diversity_adjusted_score, cfg.safety, upstream_reasons)
        reasons.extend(outcome.reason_codes)
        if outcome.blocked:
            blocked.append(BlockedRecord(cycle_id=candidate.cycle_id, decision_time=candidate.decision_time, comparison_group_id=candidate.comparison_group_id, candidate_id=candidate.candidate_id, reason_codes=outcome.reason_codes, evidence_ids=outcome.evidence_ids, policy_version=cfg.safety.policy_id, lineage_id=candidate.lineage_id))
        else:
            eligible.append(DecisionRecord(cycle_id=candidate.cycle_id, decision_time=candidate.decision_time, comparison_group_id=candidate.comparison_group_id, candidate_id=candidate.candidate_id, decision="ELIGIBLE", reason_codes=(), evidence_ids=outcome.evidence_ids, policy_version=cfg.safety.policy_id, lineage_id=candidate.lineage_id))
    base = bundle.manifest
    audit = AuditRecord(cycle_id=base.cycle_id, decision_time=base.decision_time, module_id=MODULE_ID, counts={"received": len(bundle.candidates), "eligible": len(eligible), "blocked": len(blocked)}, reason_code_distribution=dict(Counter(reasons)), policy_version=cfg.safety.policy_id, lineage_id=base.lineage_id)
    outputs = (
        artifact_from_records(name="safety_eligible_candidate_panel", schema_version="2.0.0", module_id=MODULE_ID, runtime=cfg.runtime, cycle_id=base.cycle_id, decision_time=base.decision_time, lineage_id=base.lineage_id, records=eligible),
        artifact_from_records(name="safety_blocked_candidate_panel", schema_version="2.0.0", module_id=MODULE_ID, runtime=cfg.runtime, cycle_id=base.cycle_id, decision_time=base.decision_time, lineage_id=base.lineage_id, records=blocked),
        artifact_from_records(name="safety_gate_audit_report", schema_version="2.0.0", module_id=MODULE_ID, runtime=cfg.runtime, cycle_id=base.cycle_id, decision_time=base.decision_time, lineage_id=base.lineage_id, records=(audit,)),
    )
    module_receipt = receipt(module_id=MODULE_ID, runtime=cfg.runtime, cycle_id=base.cycle_id, inputs=(base, score_envelope), outputs=outputs, counts=audit.counts, reason_codes=reasons, policy_versions={"safety": cfg.safety.policy_id}, timer=timer)
    return {item.artifact_name: item.model_dump(mode="json") for item in outputs} | {"module_execution_receipt": module_receipt.model_dump(mode="json")}
