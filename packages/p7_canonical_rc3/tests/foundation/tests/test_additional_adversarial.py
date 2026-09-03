from copy import deepcopy
import math

import pytest

from quant_pipeline.phase_07_strategy_tournament.foundation.canonical import content_sha256
from quant_pipeline.phase_07_strategy_tournament.foundation.errors import P7S1Error
from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S1_M01_phase6_handoff_contract_validator import run_module as run_m01
from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S1_M02_candidate_artifact_reconciliation_engine import run_module as run_m02
from quant_pipeline.phase_07_strategy_tournament.foundation.modules.P7_S1_M03_temporal_integrity_and_forbidden_field_firewall import run_module as run_m03


def _rehash_artifact_and_ref(manifest, artifact):
    base = {key: value for key, value in artifact.items() if key != "content_sha256"}
    artifact["content_sha256"] = content_sha256(base)
    ref = next(row for row in manifest["artifacts"] if row["artifact_name"] == artifact["artifact_name"])
    ref["content_sha256"] = artifact["content_sha256"]
    ref["record_count"] = artifact["record_count"]


def _bundle(p6_fixture, module_config):
    manifest, artifacts = p6_fixture
    index = run_m01(
        {"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts},
        module_config,
    )["outputs"]["verified_p6_artifact_index"]
    return run_m02({"verified_p6_artifact_index": index}, module_config)["outputs"]["validated_strategy_candidate_bundle"]


def test_rejects_duplicate_primary_candidate(p6_fixture, module_config):
    manifest, artifacts = deepcopy(p6_fixture)
    panel = next(row for row in artifacts if row["artifact_name"] == "strategy_candidate_panel")
    panel["records"].append(deepcopy(panel["records"][0]))
    panel["record_count"] = 2
    _rehash_artifact_and_ref(manifest, panel)
    index = run_m01(
        {"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts},
        module_config,
    )["outputs"]["verified_p6_artifact_index"]
    with pytest.raises(P7S1Error) as exc_info:
        run_m02({"verified_p6_artifact_index": index}, module_config)
    assert exc_info.value.code == "P7_CANDIDATE_PRIMARY_DUPLICATE"


def test_rejects_missing_mandatory_child(p6_fixture, module_config):
    manifest, artifacts = deepcopy(p6_fixture)
    panel = next(row for row in artifacts if row["artifact_name"] == "strategy_risk_panel")
    panel["records"] = []
    panel["record_count"] = 0
    _rehash_artifact_and_ref(manifest, panel)
    index = run_m01(
        {"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts},
        module_config,
    )["outputs"]["verified_p6_artifact_index"]
    with pytest.raises(P7S1Error) as exc_info:
        run_m02({"verified_p6_artifact_index": index}, module_config)
    assert exc_info.value.code == "P7_CANDIDATE_MANDATORY_RECORD_MISSING"


def test_rejects_capability_claim_without_records(p6_fixture, module_config):
    manifest, artifacts = deepcopy(p6_fixture)
    panel = next(row for row in artifacts if row["artifact_name"] == "strategy_candidate_panel")
    panel["records"][0]["capabilities"]["greeks"] = "AVAILABLE"
    _rehash_artifact_and_ref(manifest, panel)
    index = run_m01(
        {"phase7_strategy_handoff_manifest": manifest, "declared_p6_artifacts": artifacts},
        module_config,
    )["outputs"]["verified_p6_artifact_index"]
    with pytest.raises(P7S1Error) as exc_info:
        run_m02({"verified_p6_artifact_index": index}, module_config)
    assert exc_info.value.code == "P7_CAPABILITY_STATUS_INCONSISTENT"


def test_rejects_naive_nested_timestamp(p6_fixture, module_config):
    bundle = _bundle(p6_fixture, module_config)
    bundle["records"][0]["candidate"]["quote_time"] = "2026-01-05T14:00:00"
    with pytest.raises(P7S1Error) as exc_info:
        run_m03({"validated_strategy_candidate_bundle": bundle}, module_config)
    assert exc_info.value.code == "P7_NAIVE_TIMESTAMP"


def test_rejects_nonfinite_wire_value(p6_fixture, module_config):
    bundle = _bundle(p6_fixture, module_config)
    bundle["records"][0]["risk"]["bad_metric"] = math.inf
    with pytest.raises(P7S1Error) as exc_info:
        run_m03({"validated_strategy_candidate_bundle": bundle}, module_config)
    assert exc_info.value.code == "P7_NONFINITE_WIRE_VALUE"
