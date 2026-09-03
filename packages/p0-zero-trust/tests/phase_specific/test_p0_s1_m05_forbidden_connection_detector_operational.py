from copy import deepcopy
from pathlib import Path
import hashlib
import json
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = ROOT.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S1_M05_forbidden_connection_detector import (
    ContractValidationError,
    run_module,
)


FORBIDDEN_MATRIX = ROOT / "contracts" / "CONNECTIONS.yaml"
# Only the package-root matrix is active. Nested assets/foundation/economic and
# documentary copies are historical or scoped matrices and must not be merged
# into the global topology.
IO_PATHS = sorted(
    path
    for path in WORKSPACE_ROOT.glob("phase_*/**/contracts/MODULE_IO_MATRIX.yaml")
    if path.parent.name == "contracts"
    and path.parent.parent.name.endswith("_agent_package_RC4_1")
)


def io_matrices():
    return [yaml.safe_load(path.read_text(encoding="utf-8")) for path in IO_PATHS]


def declared_edges(matrices):
    return sorted(
        {
            (module["module_id"], target)
            for matrix in matrices
            for module in matrix["module_io_matrix"]
            for target in module.get("emits_to", {}).get("modules", [])
        }
    )


def validated_connection_matrix(matrices=None):
    matrices = matrices or io_matrices()
    edges = declared_edges(matrices)
    digest = hashlib.sha256(json.dumps(edges).encode("utf-8")).hexdigest()
    return {
        "artifact_id": f"validated-connection-matrix-{digest[:12]}",
        "pipeline_version": "V14.1-RC4.1",
        "lineage_id": f"sha256:{digest}",
        "connection_count": len(edges),
        "connections": [
            {"source_module": source, "target_module": target}
            for source, target in edges
        ],
        "promotion_blocked": True,
    }


def valid_inputs(matrices=None):
    matrices = matrices or io_matrices()
    return {
        "validated_connection_matrix": validated_connection_matrix(matrices),
        "forbidden_connection_matrix_yaml": str(FORBIDDEN_MATRIX),
        "module_io_matrix_all_phases": matrices,
    }


def module(matrices, module_id):
    return next(
        item
        for matrix in matrices
        for item in matrix["module_io_matrix"]
        if item["module_id"] == module_id
    )


def test_real_all_phase_topology_is_clean_and_fully_evaluated():
    assert len(IO_PATHS) == 10
    result = run_module(
        valid_inputs(),
        {"pipeline_version": "V14.1-RC4.1", "created_at": "2026-07-19T00:00:00Z"},
    )
    report = result["outputs"]["forbidden_connection_report"]

    assert result["module_id"] == "P0.S1.M05"
    assert report["evaluated_connection_count"] == report["declared_connection_count"]
    assert report["declared_connection_count"] == len(declared_edges(io_matrices()))
    assert report["forbidden_connections"] == 0
    assert report["findings"] == []
    assert report["status"] == "PASS"
    assert report["severity"] == "NONE"
    assert report["release_blocking"] is False
    assert report["no_forbidden_economic_connection"] is True
    assert report["phase0_not_economic_input"] is True
    assert report["connection_matrix_consistent"] is True
    assert report["promotion_blocked"] is True


def test_forbidden_p0_to_economic_edge_produces_structured_blocking_findings():
    matrices = io_matrices()
    module(matrices, "P0.S1.M01")["emits_to"]["modules"].append("P8.S1.M01")
    module(matrices, "P8.S1.M01")["consumes_from"]["modules"].append("P0.S1.M01")
    report = run_module(valid_inputs(matrices), {})["outputs"]["forbidden_connection_report"]

    rules = {finding["rule_id"] for finding in report["findings"]}
    assert rules == {"EXPLICIT_FORBIDDEN_CONNECTION", "P0_ECONOMIC_INPUT"}
    assert report["forbidden_connection_count"] == 2
    assert report["critical_finding_count"] == 2
    assert report["warning_finding_count"] == 0
    assert report["status"] == "FAIL"
    assert report["severity"] == "CRITICAL"
    assert report["release_blocking"] is True
    assert report["no_forbidden_economic_connection"] is False
    assert report["phase0_not_economic_input"] is False
    assert all(finding["release_blocking"] for finding in report["findings"])
    assert all(finding["finding_id"].startswith("FC-") for finding in report["findings"])


def test_p0_artifact_consumed_by_economic_phase_is_release_blocking():
    matrices = io_matrices()
    module(matrices, "P1.S1.M01")["consumes_from"]["artifacts"].append(
        "validated_phase_registry"
    )
    report = run_module(valid_inputs(matrices), {})["outputs"]["forbidden_connection_report"]
    finding = next(item for item in report["findings"] if item["artifact"] == "validated_phase_registry")
    assert finding["rule_id"] == "P0_ECONOMIC_INPUT"
    assert finding["source_module"] == "P0"
    assert finding["target_module"] == "P1.S1.M01"
    assert report["release_blocking"] is True


def test_extra_validated_edge_is_reported_as_matrix_violation():
    inputs = valid_inputs()
    inputs["validated_connection_matrix"]["connections"].append(
        {"source_module": "P1.S1.M01", "target_module": "P2.S1.M01"}
    )
    inputs["validated_connection_matrix"]["connection_count"] += 1
    report = run_module(inputs, {})["outputs"]["forbidden_connection_report"]
    assert {item["rule_id"] for item in report["findings"]} == {
        "UNDECLARED_VALIDATED_EDGE"
    }
    assert report["connection_matrix_consistent"] is False
    assert report["release_blocking"] is True


def test_missing_validated_edge_is_reported_as_matrix_violation():
    inputs = valid_inputs()
    inputs["validated_connection_matrix"]["connections"].pop()
    inputs["validated_connection_matrix"]["connection_count"] -= 1
    report = run_module(inputs, {})["outputs"]["forbidden_connection_report"]
    assert {item["rule_id"] for item in report["findings"]} == {
        "VALIDATED_EDGE_MISSING"
    }
    assert report["release_blocking"] is True


def test_emitter_consumer_asymmetry_is_detected_fail_closed():
    matrices = io_matrices()
    edge = declared_edges(matrices)[0]
    module(matrices, edge[1])["consumes_from"]["modules"].remove(edge[0])
    inputs = valid_inputs(matrices)
    inputs["validated_connection_matrix"] = validated_connection_matrix(io_matrices())
    report = run_module(inputs, {})["outputs"]["forbidden_connection_report"]
    rules = {item["rule_id"] for item in report["findings"]}
    assert "IO_MATRIX_ASYMMETRY" in rules
    assert "UNDECLARED_VALIDATED_EDGE" in rules
    assert report["connection_matrix_consistent"] is False
    assert report["release_blocking"] is True


@pytest.mark.parametrize(
    "mutation,expected",
    [
        (lambda value: value.clear(), "missing fields"),
        (lambda value: value.__setitem__("pipeline_version", "V15.0"), "pipeline version"),
        (lambda value: value.__setitem__("lineage_id", "not-a-hash"), "lineage_id"),
        (lambda value: value.__setitem__("connections", []), "materialized connections"),
    ],
)
def test_rejects_invalid_validated_connection_matrix(mutation, expected):
    inputs = valid_inputs()
    mutation(inputs["validated_connection_matrix"])
    with pytest.raises(ContractValidationError, match=expected):
        run_module(inputs, {})


def test_rejects_invalid_forbidden_rule_matrix():
    inputs = valid_inputs()
    inputs["forbidden_connection_matrix_yaml"] = {"forbidden_connections": ["bad-rule"]}
    with pytest.raises(ContractValidationError, match="invalid forbidden connection rule"):
        run_module(inputs, {})


def test_rejects_io_bundle_without_all_ten_phases():
    inputs = valid_inputs()
    inputs["module_io_matrix_all_phases"] = inputs["module_io_matrix_all_phases"][:-1]
    with pytest.raises(ContractValidationError, match="does not cover the active release scope"):
        run_module(inputs, {})


def test_rejects_ten_phase_bundle_with_incomplete_module_topology():
    inputs = valid_inputs()
    for matrix in inputs["module_io_matrix_all_phases"]:
        matrix["module_io_matrix"] = matrix["module_io_matrix"][:1]
    with pytest.raises(ContractValidationError, match="active canonical modules"):
        run_module(inputs, {})


def test_rejects_forbidden_fields_recursively():
    inputs = valid_inputs()
    inputs["module_io_matrix_all_phases"][0]["metadata"] = {
        "nested": [{"portfolio_weight": 0.5}]
    }
    with pytest.raises(ContractValidationError, match="forbidden input fields detected"):
        run_module(inputs, {})


def test_rejects_symbolic_placeholder_and_non_mapping_config():
    inputs = valid_inputs()
    inputs["validated_connection_matrix"] = {"source": "validated_connection_matrix"}
    with pytest.raises(ContractValidationError, match="symbolic placeholder"):
        run_module(inputs, {})
    with pytest.raises(ContractValidationError, match="config must be a dict"):
        run_module(valid_inputs(), [])


def test_output_conforms_to_structured_schema():
    schema = yaml.safe_load(
        (ROOT / "schemas" / "forbidden_connection_report.schema.yaml").read_text(
            encoding="utf-8"
        )
    )
    report = run_module(
        valid_inputs(), {"created_at": "2026-07-19T00:00:00Z"}
    )["outputs"]["forbidden_connection_report"]
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(report) == set(schema["properties"])
    assert set(schema["required_fields"]) == set(schema["properties"])
    finding_schema = schema["properties"]["findings"]["items"]
    assert finding_schema["additionalProperties"] is False
    assert finding_schema["properties"]["severity"]["const"] == "CRITICAL"
