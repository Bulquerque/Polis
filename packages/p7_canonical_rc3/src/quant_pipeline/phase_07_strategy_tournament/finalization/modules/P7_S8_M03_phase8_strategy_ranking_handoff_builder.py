"""P7.S8.M03 — strict P8 handoff with no economic defaults."""
from __future__ import annotations

from typing import Mapping

from ..application.phase8_publication import build_phase8_artifacts, load_publication_inputs
from ..application.s8_reconciliation import load_s8_bundle
from ..application.runtime import Timer, receipt
from ..boundary.s8_config import S8Config

MODULE_ID = "P7.S8.M03"


def run_module(inputs: Mapping[str, object], config: Mapping[str, object]) -> dict[str, object]:
    timer = Timer()
    cfg = S8Config.model_validate(config)
    bundle = load_s8_bundle(inputs, MODULE_ID, cfg.forbidden_fields)
    loaded = load_publication_inputs(inputs, MODULE_ID)
    artifacts = build_phase8_artifacts(bundle, loaded, cfg, MODULE_ID)
    compatibility = artifacts[1]
    reasons = [row.get("reason_code") for row in compatibility.records if row.get("reason_code")]
    module_receipt = receipt(
        module_id=MODULE_ID, runtime=cfg.runtime, cycle_id=bundle.manifest.cycle_id,
        inputs=(bundle.manifest, loaded.ranked_env, loaded.thesis_env, loaded.audit_env,
                loaded.trace_env, loaded.tie_env, loaded.summary_env,
                bundle.artifacts["score_decomposition_panel"]),
        outputs=artifacts,
        counts={"ranked": len(loaded.ranked), "snapshots": artifacts[0].record_count,
                "compatibility_supported": sum(
                    row.get("projection_status") == "SUPPORTED" for row in compatibility.records
                )},
        reason_codes=reasons, policy_versions={"publication": cfg.publication.policy_id}, timer=timer,
    )
    return {item.artifact_name: item.model_dump(mode="json") for item in artifacts} | {
        "module_execution_receipt": module_receipt.model_dump(mode="json")
    }
