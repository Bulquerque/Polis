from __future__ import annotations

import json

from datetime import UTC, datetime

from quant_pipeline.phase_09.contracts.base import ModuleStatus
from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.clock import FixedClock
from quant_pipeline.phase_09.subphases.s02_experiment_governance.runner import EXPECTED_MODULE_IDS, S2Runner


def test_full_runner_closes_all_modules(result) -> None:
    outputs = result.s2_outputs
    assert outputs.subphase_receipt.payload.status is ModuleStatus.SUCCESS
    assert tuple(r.payload.module_id for r in outputs.module_receipts) == EXPECTED_MODULE_IDS
    assert all(r.payload.status is ModuleStatus.SUCCESS for r in outputs.module_receipts)
    assert result.foundation_bundle is not None
    assert result.foundation_bundle.payload.contract_name == "P9_FOUNDATION_EXPERIMENT_BUNDLE_V1"


def test_invalid_spec_skips_downstream(s2_request) -> None:
    raw = s2_request.model_dump(mode="json")
    raw["specification"]["development_dataset_ids"] = raw["specification"]["final_holdout_dataset_ids"]
    req = type(s2_request).model_validate_json(json.dumps(raw))
    result = S2Runner(clock=FixedClock(datetime(2026,1,7,15,0,tzinfo=UTC))).run(req)
    assert result.foundation_bundle is None
    assert result.s2_outputs.module_receipts[0].payload.status is ModuleStatus.INVALID
    assert all(r.payload.status is ModuleStatus.SKIPPED_UPSTREAM_BLOCKED for r in result.s2_outputs.module_receipts[1:])


def test_s1_failure_blocks_all_s2(s2_request) -> None:
    raw = s2_request.model_dump(mode="json")
    raw["s1_outputs"]["subphase_receipt"]["payload"]["status"] = "INVALID"
    raw["s1_outputs"]["subphase_receipt"]["payload"]["reason_codes"] = ["P9_S1_TEST_INVALID"]
    # update integrity by reusing S1 helper through normal model construction is non-trivial;
    # this test proves the runner gate using an already valid model copy.
    s1 = s2_request.s1_outputs.model_copy(deep=True)
    payload = s1.subphase_receipt.payload.model_copy(update={"status": ModuleStatus.INVALID, "reason_codes": ("P9_S1_TEST_INVALID",)})
    from quant_pipeline.phase_09.contracts.integrity import IntegrityEnvelope, payload_sha256
    receipt = s1.subphase_receipt.model_copy(update={"payload": payload, "integrity": IntegrityEnvelope(payload_sha256=payload_sha256(payload))})
    s1 = s1.model_copy(update={"subphase_receipt": receipt})
    req = s2_request.model_copy(update={"s1_outputs": s1})
    result = S2Runner(clock=FixedClock(datetime(2026,1,7,15,0,tzinfo=UTC))).run(req)
    assert result.foundation_bundle is None
    assert all(r.payload.status is ModuleStatus.SKIPPED_UPSTREAM_BLOCKED for r in result.s2_outputs.module_receipts)


def test_bundle_hashes_match_outputs(result) -> None:
    from quant_pipeline.phase_09.contracts.integrity import payload_sha256
    bundle = result.foundation_bundle
    assert bundle.payload.s1_outputs_sha256 == payload_sha256(bundle.payload.s1_outputs)
    assert bundle.payload.s2_outputs_sha256 == payload_sha256(bundle.payload.s2_outputs)
