"""P7.S7.M04 — split candidates into rankable, abstained and blocked."""
from __future__ import annotations

from typing import Mapping

from ..application.module_io import parse_envelope, parse_records
from ..application.rankability_publication import handoff_manifest, output_artifacts
from ..application.reconciliation import load_scoring_bundle
from ..application.runtime import Timer, receipt
from ..boundary.config import S7Config
from ..boundary.outputs import BlockedRecord, DecisionRecord, DiversityAdjustedScoreRecord
from ..subphases.s7_safety_diversity.rankability import build_rankability

MODULE_ID = "P7.S7.M04"


def run_module(inputs: Mapping[str, object], config: Mapping[str, object]) -> dict[str, object]:
    timer = Timer()
    cfg = S7Config.model_validate(config)
    bundle = load_scoring_bundle(inputs, MODULE_ID, cfg.forbidden_fields)
    eligible_env = parse_envelope(inputs, "safety_eligible_candidate_panel", MODULE_ID)
    blocked_env = parse_envelope(inputs, "safety_blocked_candidate_panel", MODULE_ID)
    score_env = parse_envelope(inputs, "diversity_adjusted_score_panel", MODULE_ID)
    cluster_env = parse_envelope(inputs, "candidate_diversity_cluster_panel", MODULE_ID)
    eligible = parse_records(eligible_env, DecisionRecord, MODULE_ID)
    blocked = parse_records(blocked_env, BlockedRecord, MODULE_ID)
    adjusted = {
        item.candidate_id: item
        for item in parse_records(score_env, DiversityAdjustedScoreRecord, MODULE_ID)
    }
    outputs = build_rankability(
        bundle.candidates, {item.candidate_id for item in eligible},
        {item.candidate_id: item for item in blocked}, adjusted,
        cfg.abstention, bundle.manifest.lineage_id,
    )
    artifacts = output_artifacts(bundle, outputs, cfg, MODULE_ID)
    artifacts.append(handoff_manifest(bundle, outputs, artifacts, score_env, cluster_env, cfg, MODULE_ID))
    reasons = list(outputs.reason_codes) + [code for item in outputs.blocked for code in item.reason_codes]
    module_receipt = receipt(
        module_id=MODULE_ID, runtime=cfg.runtime, cycle_id=bundle.manifest.cycle_id,
        inputs=(bundle.manifest, eligible_env, blocked_env, score_env, cluster_env), outputs=artifacts,
        counts={"received": len(bundle.candidates), "rankable": len(outputs.rankable),
                "abstained": len(outputs.abstained), "blocked": len(outputs.blocked)},
        reason_codes=reasons, policy_versions={"abstention": cfg.abstention.policy_id}, timer=timer,
    )
    return {item.artifact_name: item.model_dump(mode="json") for item in artifacts} | {
        "module_execution_receipt": module_receipt.model_dump(mode="json")
    }
