"""P7.S8.M02 — structured thesis cards, decision traces and audit."""
from __future__ import annotations

from typing import Mapping

from ..application.s8_reconciliation import load_s8_bundle
from ..application.runtime import Timer, artifact_from_records, receipt
from ..application.thesis_publication import build_audit_record, build_thesis_artifacts, load_ranking_inputs
from ..boundary.s8_config import S8Config

MODULE_ID = "P7.S8.M02"


def run_module(inputs: Mapping[str, object], config: Mapping[str, object]) -> dict[str, object]:
    timer = Timer()
    cfg = S8Config.model_validate(config)
    bundle = load_s8_bundle(inputs, MODULE_ID, cfg.forbidden_fields)
    loaded = load_ranking_inputs(inputs, MODULE_ID)
    thesis_env, trace_env = build_thesis_artifacts(bundle, loaded, cfg, MODULE_ID)
    input_envs = (bundle.manifest, loaded.ranked_env, loaded.tie_env, loaded.summary_env, *bundle.artifacts.values())
    audit = build_audit_record(bundle, loaded, input_envs, (loaded.ranked_env, thesis_env, trace_env), cfg)
    audit_env = artifact_from_records(
        name="ranking_audit_report", schema_version="2.0.0", module_id=MODULE_ID,
        runtime=cfg.runtime, cycle_id=bundle.manifest.cycle_id,
        decision_time=bundle.manifest.decision_time, lineage_id=bundle.manifest.lineage_id, records=(audit,),
    )
    artifacts = (thesis_env, trace_env, audit_env)
    module_receipt = receipt(
        module_id=MODULE_ID, runtime=cfg.runtime, cycle_id=bundle.manifest.cycle_id,
        inputs=input_envs, outputs=artifacts,
        counts={"ranked": len(loaded.ranked), "thesis_cards": thesis_env.record_count,
                "traces": trace_env.record_count},
        reason_codes=(), policy_versions={"ranking": cfg.ranking.policy_id,
                                          "thesis": cfg.thesis.policy_id}, timer=timer,
    )
    return {item.artifact_name: item.model_dump(mode="json") for item in artifacts} | {
        "module_execution_receipt": module_receipt.model_dump(mode="json")
    }
