from pathlib import Path
import ast

from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S4_M01_test_report_collector import run_module as collect
from quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S4_M04_test_status_aggregator import run_module as aggregate


ROOT = Path(__file__).resolve().parents[2]
MODULES = ROOT / "src/quant_pipeline/phase_00_zero_trust_guardian/modules"
LINEAGE = "sha256:" + "a" * 64
FAMILIES = (
    "test_run_report_all_phases",
    "contract_test_report_all_phases",
    "schema_test_report_all_phases",
    "code_quality_test_report_all_phases",
)


def _reports_without_p9():
    return {
        family: [
            {
                "test_run_id": f"{family}-P{i}",
                "phase_id": f"P{i}",
                "total_tests": 1,
                "passed_tests": 1,
                "failed_tests": 0,
                "skipped_tests": 0,
                "status": "PASS",
            }
            for i in range(9)
        ]
        for family in FAMILIES
    }


def test_reformed_s4_respects_clean_code_limits():
    files = sorted(MODULES.glob("P0_S4_*.py")) + sorted(MODULES.glob("_p0_s4_*.py"))
    assert files
    for path in files:
        source = path.read_text(encoding="utf-8")
        assert len(source.splitlines()) <= 350, path.name
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.end_lineno - node.lineno + 1 <= 60, f"{path.name}:{node.name}"


def test_not_started_phase_flows_through_collector_and_aggregator_without_false_failure():
    lifecycle = {**{f"P{i}": "IMPLEMENTED" for i in range(9)}, "P9": "NOT_STARTED"}
    collected = collect(
        _reports_without_p9(),
        {"created_at": "2026-01-01T00:00:00Z", "phase_lifecycle_statuses": lifecycle},
    )["outputs"]["collected_test_reports"]
    inputs = {
        "collected_test_reports": collected,
        "contract_test_report": {"artifact_id": "contract", "status": "PASS", "release_blocking": False, "lineage_id": LINEAGE},
        "schema_test_report": {"artifact_id": "schema", "status": "PASS", "release_blocking": False, "lineage_id": LINEAGE},
    }
    outputs = aggregate(inputs)["outputs"]
    p9 = next(item for item in outputs["phase_test_status_panel"]["phases"] if item["phase_id"] == "P9")
    assert p9["test_status"] == "NOT_RUN"
    assert not p9["release_blocking"]
    assert outputs["global_test_report"]["status"] == "PASS"


def test_s4_contract_specs_exist_and_are_not_global_schemas():
    specs = sorted((ROOT / "contracts").glob("P0_S4_*.spec.yaml"))
    assert {path.name for path in specs} == {
        "P0_S4_SCHEMA_FIXTURE_POLICY.spec.yaml",
        "P0_S4_TEST_EXPECTATION_POLICY.spec.yaml",
        "P0_S4_ZERO_TRUST_EVIDENCE_REQUIREMENTS.spec.yaml",
    }
    assert not list((ROOT / "contracts").glob("P0_S4_*.schema.yaml"))


def test_public_s4_module_identity_is_preserved():
    expected = {
        "P0_S4_M01_test_report_collector.py",
        "P0_S4_M02_contract_test_orchestrator.py",
        "P0_S4_M03_schema_test_orchestrator.py",
        "P0_S4_M04_test_status_aggregator.py",
        "P0_S4_M05_evidence_package_builder.py",
    }
    assert {path.name for path in MODULES.glob("P0_S4_M0*.py")} == expected
