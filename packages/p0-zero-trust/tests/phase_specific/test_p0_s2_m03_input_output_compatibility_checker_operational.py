from copy import deepcopy
from importlib import import_module
from pathlib import Path
import hashlib
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = ROOT.parents[1]
GLOBAL_ROOT = (
    REPOSITORY_ROOT
    / "global_contracts_parallel_agents"
    / "v14_1_global_contracts_parallel_agents_RC4_1"
)
PACKAGE_ROOT = "quant_pipeline.phase_00_zero_trust_guardian.modules"

sys.path.insert(0, str(ROOT / "src"))
m01 = import_module(f"{PACKAGE_ROOT}.P0_S2_M01_contract_registry_builder")
m02 = import_module(f"{PACKAGE_ROOT}.P0_S2_M02_schema_registry_builder")
m04 = import_module(f"{PACKAGE_ROOT}.P0_S1_M04_connection_matrix_validator")
s1m01 = import_module(f"{PACKAGE_ROOT}.P0_S1_M01_phase_registry_loader")
s1m02 = import_module(f"{PACKAGE_ROOT}.P0_S1_M02_subphase_registry_loader")
s1m03 = import_module(f"{PACKAGE_ROOT}.P0_S1_M03_module_registry_loader")
module = import_module(f"{PACKAGE_ROOT}.P0_S2_M03_input_output_compatibility_checker")


def _schema_inventory():
    return sorted(REPOSITORY_ROOT.glob("global_contracts_parallel_agents/**/*.schema.yaml")) + sorted(
        REPOSITORY_ROOT.glob("phase_*/**/*.schema.yaml")
    )


def _current_contract_manifest():
    path = GLOBAL_ROOT / "source_of_truth" / "registries" / "module_registry.yaml"
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    # Worktree modules can advance before the coordinator serially regenerates
    # the canonical registry. The operational fixture binds to current real bytes.
    for entry in manifest["modules"]:
        contract = REPOSITORY_ROOT / entry["contract_path"]
        entry["contract_sha256"] = hashlib.sha256(contract.read_bytes()).hexdigest()
    return manifest


def _real_inputs():
    config = {"pipeline_version": "V14.1-RC4.1", "created_at": "2026-07-19T00:00:00Z"}
    contract_registry = m01.run_module(
        {
            "contracts_all_phases": _current_contract_manifest(),
            "global_contracts": GLOBAL_ROOT / "contracts",
        },
        config,
    )["outputs"]["contract_registry"]
    schema_registry = m02.run_module(
        {"schemas_all_phases": [str(path) for path in _schema_inventory()]},
        config,
    )["outputs"]["schema_registry"]

    phase_registry = s1m01.run_module(
        {
            "phase_registry_yaml": ROOT / "source_of_truth" / "registries" / "phase_registry.yaml",
            "global_architecture_config": {
                "authority": "global_master",
                "pipeline_version": "V14.1-RC4.1",
                "phase_registry_id": "phase_registry_v14_1_rc4_1",
            },
        },
        config,
    )["outputs"]["validated_phase_registry"]
    subphase_registry = s1m02.run_module(
        {
            "validated_phase_registry": phase_registry,
            "subphase_registry_yaml": ROOT / "source_of_truth" / "registries" / "subphase_registry.yaml",
        },
        config,
    )["outputs"]["validated_subphase_registry"]
    module_registry = s1m03.run_module(
        {
            "validated_phase_registry": phase_registry,
            "validated_subphase_registry": subphase_registry,
            "module_registry_yaml": ROOT / "source_of_truth" / "registries" / "module_registry.yaml",
        },
        config,
    )["outputs"]["validated_module_registry"]
    matrix = m04.run_module(
        {
            "connection_matrix_yaml": str(ROOT / "contracts" / "MODULE_IO_MATRIX.yaml"),
            "validated_phase_registry": phase_registry,
            "validated_module_registry": module_registry,
        },
        config,
    )["outputs"]["validated_connection_matrix"]
    return {
        "contract_registry": contract_registry,
        "schema_registry": schema_registry,
        "validated_connection_matrix": matrix,
    }


@pytest.fixture(scope="module")
def real_inputs():
    return _real_inputs()


def _run(inputs):
    return module.run_module(
        inputs,
        {"pipeline_version": "V14.1-RC4.1", "created_at": "2026-07-19T00:00:00Z"},
    )["outputs"]


def _contract(registry, module_id):
    return next(item for item in registry["contracts"] if item["module_id"] == module_id)


def test_m03_compares_all_real_contracts_schemas_and_p0_connections(real_inputs):
    outputs = _run(real_inputs)
    io_report = outputs["io_compatibility_report"]
    schema_report = outputs["schema_compatibility_report"]

    assert io_report["checked_contract_count"] == real_inputs["contract_registry"]["contract_count"]
    assert io_report["checked_matrix_module_count"] == 40
    assert io_report["checked_matrix_connection_count"] > 40
    assert len(io_report["compatibility_checks"]) > 500
    assert io_report["incompatible_check_count"] == 0
    assert io_report["output_covers_required_input"] is True
    assert io_report["optional_feedback_not_blocking"] is True
    assert io_report["status"] == "PASS"
    assert io_report["release_blocking"] is False

    assert schema_report["checked_authority_schema_count"] == len(real_inputs["schema_registry"]["schemas"])
    assert len(schema_report["schema_checks"]) == 232
    assert schema_report["finding_count"] == 0
    assert schema_report["status"] == "PASS"
    assert schema_report["release_blocking"] is False
    assert schema_report["findings"] == []


def test_m03_records_real_producer_consumer_and_required_field_types(real_inputs):
    outputs = _run(real_inputs)
    checks = outputs["io_compatibility_report"]["compatibility_checks"]
    assert any(
        item["producer"] == "P0.S1.M02"
        and item["consumer"] == "P0.S1.M03"
        and item["artifact"] == "validated_subphase_registry"
        and item["status"] == "COMPATIBLE"
        for item in checks
    )
    schema_check = next(
        item
        for item in outputs["schema_compatibility_report"]["schema_checks"]
        if item["artifact"] == "io_compatibility_report"
    )
    assert schema_check["required_fields"]
    assert schema_check["field_types"]
    assert schema_check["mirror_status"] == "MATCH"


def test_optional_feedback_is_explicit_and_never_release_blocking(real_inputs):
    outputs = _run(real_inputs)
    optional = [
        item
        for item in outputs["io_compatibility_report"]["compatibility_checks"]
        if item["status"] == "OPTIONAL"
    ]
    assert optional
    assert all(item["source_kind"] == "optional_feedback" for item in optional)
    assert all(item["release_blocking"] is False for item in optional)
    assert any(item["artifact"] and item["consumer"] for item in optional)


def test_missing_required_producer_becomes_structured_release_blocker(real_inputs):
    inputs = deepcopy(real_inputs)
    producer = _contract(inputs["contract_registry"], "P0.S1.M02")
    producer["outputs"].remove("validated_subphase_registry")
    producer["emits_to"]["artifacts"].remove("validated_subphase_registry")
    producer["output_schemas"] = [
        item for item in producer["output_schemas"] if item["artifact"] != "validated_subphase_registry"
    ]
    report = _run(inputs)["io_compatibility_report"]
    assert report["status"] == "FAIL"
    assert report["release_blocking"] is True
    finding = next(
        item
        for item in report["findings"]
        if item["code"] == "REQUIRED_ARTIFACT_PRODUCER_MISMATCH"
    )
    assert finding["artifact"] == "validated_subphase_registry"
    assert finding["consumer"] == "P0.S1.M03"
    assert finding["severity"] == "CRITICAL"


def test_matrix_contract_mismatch_becomes_release_blocker(real_inputs):
    inputs = deepcopy(real_inputs)
    row = next(
        item
        for item in inputs["validated_connection_matrix"]["module_io_matrix"]
        if item["module_id"] == "P0.S1.M03"
    )
    row["emits_to"]["modules"].remove("P0.S1.M04")
    report = _run(inputs)["io_compatibility_report"]
    assert report["release_blocking"] is True
    assert "MATRIX_CONTRACT_CONNECTION_MISMATCH" in {
        finding["code"] for finding in report["findings"]
    }


def test_missing_authority_schema_becomes_structured_release_blocker(real_inputs):
    inputs = deepcopy(real_inputs)
    inputs["schema_registry"]["schemas"] = [
        item
        for item in inputs["schema_registry"]["schemas"]
        if item["artifact_name"] != "validated_phase_registry"
    ]
    inputs["schema_registry"]["authority_schema_count"] -= 1
    report = _run(inputs)["schema_compatibility_report"]
    finding = next(
        item
        for item in report["findings"]
        if item["code"] == "REQUIRED_ARTIFACT_SCHEMA_MISSING"
        and item["artifact"] == "validated_phase_registry"
    )
    assert finding["release_blocking"] is True
    assert report["release_blocking"] is True


@pytest.mark.parametrize(
    "input_name",
    ["contract_registry", "schema_registry", "validated_connection_matrix"],
)
def test_m03_rejects_placeholders(input_name, real_inputs):
    inputs = dict(real_inputs)
    inputs[input_name] = {"source": input_name}
    with pytest.raises(ValueError, match="materialized artifact, not a placeholder"):
        _run(inputs)


def test_m03_rejects_malformed_and_forbidden_inputs(real_inputs):
    inputs = deepcopy(real_inputs)
    del inputs["contract_registry"]["contracts"]
    with pytest.raises(ValueError, match="malformed; missing fields"):
        _run(inputs)

    inputs = deepcopy(real_inputs)
    inputs["schema_registry"]["metadata"] = {"nested": [{"target": "leak"}]}
    with pytest.raises(ValueError, match="forbidden input fields detected"):
        _run(inputs)


def test_local_and_global_report_schemas_are_byte_identical():
    for name in ("io_compatibility_report.schema.yaml", "schema_compatibility_report.schema.yaml"):
        local = ROOT / "schemas" / name
        global_schema = GLOBAL_ROOT / "schemas" / name
        assert local.read_bytes() == global_schema.read_bytes()


def test_recursive_schema_checker_detects_nested_type_drift(monkeypatch, real_inputs):
    helper = import_module(
        "quant_pipeline.phase_00_zero_trust_guardian.modules._s2_io_compatibility"
    )
    original = helper.load_yaml_mapping

    def mutated_loader(path, label):
        document = original(path, label)
        if "phase_00_zero_trust" in path.as_posix() and path.name == "io_compatibility_report.schema.yaml":
            document = deepcopy(document)
            document["properties"]["compatibility_checks"]["items"]["properties"]["producer"]["type"] = "integer"
        return document

    monkeypatch.setattr(helper, "load_yaml_mapping", mutated_loader)
    report = _run(real_inputs)["schema_compatibility_report"]
    assert report["status"] == "FAIL"
    finding = next(
        item for item in report["findings"]
        if item["code"] == "SCHEMA_SEMANTIC_INCOMPATIBILITY"
        and item["artifact"] == "io_compatibility_report"
    )
    assert "compatibility_checks[].producer.type" in finding["message"]
