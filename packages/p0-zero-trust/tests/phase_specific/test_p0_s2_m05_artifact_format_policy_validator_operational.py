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
POLICY_PATH = GLOBAL_ROOT / "source_of_truth" / "standards" / "ARTIFACT_FORMAT_POLICY.yaml"
PACKAGE = "quant_pipeline.phase_00_zero_trust_guardian.modules.P0_S2_M05_artifact_format_policy_validator"

sys.path.insert(0, str(ROOT / "src"))
module = import_module(PACKAGE)


def _entry(artifact_id, artifact_type, declared_format, relative_path):
    path = REPOSITORY_ROOT / relative_path
    return {
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "format": declared_format,
        "path": relative_path,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _complete(artifacts):
    return {
        "inventory_scope": "all_phase_artifacts",
        "inventory_complete": True,
        "expected_artifact_count": len(artifacts),
        "artifacts": artifacts,
    }


def _real_registry():
    artifacts = [
            _entry(
                "contract-m05",
                "contract",
                "yaml",
                "phase_00_zero_trust/phase_00_zero_trust_guardian_agent_package_RC4_1/modules/P0_S2_M05_artifact_format_policy_validator.yaml",
            ),
            _entry(
                "schema-m05",
                "schema",
                "schema.yaml",
                "phase_00_zero_trust/phase_00_zero_trust_guardian_agent_package_RC4_1/schemas/artifact_format_validation_report.schema.yaml",
            ),
            _entry("global-module-table", "manifest", "csv", "GLOBAL_MODULE_TABLE.csv"),
            _entry("project-state", "structured_report", "json", "PROJECT_STATE.json"),
            _entry("readme", "human_report", "md", "README_START_HERE.md"),
            _entry(
                "master-diagram-source",
                "diagram_source",
                "mmd",
                "global_contracts_parallel_agents/v14_1_global_contracts_parallel_agents_RC4_1/diagrams/00_economic_vs_zero_trust.mmd",
            ),
            _entry(
                "master-diagram-render",
                "diagram_render",
                "png",
                "global_contracts_parallel_agents/v14_1_global_contracts_parallel_agents_RC4_1/diagrams/00_economic_vs_zero_trust.png",
            ),
        ]
    return _complete(artifacts)


def _run(registry=None, policy=None):
    return module.run_module(
        {
            "artifact_registry": _real_registry() if registry is None else registry,
            "artifact_format_policy_yaml": POLICY_PATH if policy is None else policy,
        },
        {"pipeline_version": "V14.1-RC4.1", "created_at": "2026-07-19T00:00:00Z"},
    )["outputs"]["artifact_format_validation_report"]


def test_m05_validates_real_artifacts_against_canonical_policy():
    report = _run()
    assert report["artifact_count"] == len(report["checked_artifacts"]) == 7
    assert report["findings"] == []
    assert report["blocking_findings_count"] == 0
    assert report["status"] == "PASS"
    assert report["blocking"] is False
    assert report["format_allowed"] is True
    assert report["contracts_in_yaml"] is True
    assert report["policy_non_empty"] is True
    assert report["paths_internal"] is True
    assert report["promotion_blocked"] is True
    assert {item["actual_format"] for item in report["checked_artifacts"]} == {
        "yaml", "schema.yaml", "csv", "json", "md", "mmd", "png"
    }


def test_m05_accepts_inline_policy_deterministically():
    policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    first = _run(policy=deepcopy(policy))
    second = _run(policy=deepcopy(policy))
    assert first == second
    assert first["policy_source_path"] == "inline:artifact_format_policy_yaml"


def test_m05_rejects_partial_registry_even_when_single_item_is_valid():
    registry = _real_registry()
    registry["artifacts"] = registry["artifacts"][:1]
    with pytest.raises(ValueError, match="expected_artifact_count is inconsistent"):
        _run(registry=registry)

    registry = _real_registry()
    registry.pop("inventory_complete")
    with pytest.raises(ValueError, match="inventory_complete"):
        _run(registry=registry)


def test_m05_returns_structured_blocking_findings_for_extension_and_allowlist():
    registry = _real_registry()
    registry["artifacts"][0]["format"] = "json"
    registry["artifacts"][4]["artifact_type"] = "executable_binary"
    report = _run(registry=registry)
    assert report["status"] == "BLOCKED"
    assert report["blocking"] is True
    assert report["format_allowed"] is False
    assert report["blocking_findings_count"] == len(report["findings"]) >= 2
    assert {finding["severity"] for finding in report["findings"]} == {"blocking"}
    assert "declared_format_mismatch" in {finding["code"] for finding in report["findings"]}
    assert "artifact_type_not_allowlisted" in {finding["code"] for finding in report["findings"]}
    assert all(
        set(finding)
        == {
            "artifact_id", "path", "code", "severity", "message",
            "expected_format", "actual_format",
        }
        for finding in report["findings"]
    )


def test_m05_blocks_contract_that_is_not_yaml():
    registry = _complete(
        [
            _entry("invalid-contract", "contract", "yaml", "README_START_HERE.md")
        ]
    )
    report = _run(registry=registry)
    assert report["status"] == "BLOCKED"
    assert report["contracts_in_yaml"] is False
    assert "contract_not_yaml" in {finding["code"] for finding in report["findings"]}


def test_m05_blocks_incompatible_content_and_hash(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "REPOSITORY_ROOT", tmp_path)
    (tmp_path / "bad.json").write_text("not-json", encoding="utf-8")
    registry = _complete(
        [
            {
                "artifact_id": "bad-json",
                "artifact_type": "structured_report",
                "format": "json",
                "path": "bad.json",
                "sha256": "0" * 64,
            }
        ]
    )
    policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    report = _run(registry=registry, policy=policy)
    assert report["status"] == "BLOCKED"
    assert {finding["code"] for finding in report["findings"]} == {
        "content_format_mismatch",
        "content_hash_mismatch",
    }


def test_m05_accepts_explicit_registry_yaml_path(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "REPOSITORY_ROOT", tmp_path)
    contract = tmp_path / "contracts" / "example.yaml"
    contract.parent.mkdir(parents=True)
    contract.write_text("contract_id: example\nsource_phase: P1\ntarget_phase: P2\n", encoding="utf-8")
    registry_path = tmp_path / "artifact_registry.yaml"
    registry_path.write_text(
        yaml.safe_dump(
                _complete(
                    [
                    {
                        "artifact_id": "example-contract",
                        "artifact_type": "contract",
                        "format": "yaml",
                        "path": "contracts/example.yaml",
                    }
                    ]
                ),
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    report = _run(registry=registry_path, policy=policy)
    assert report["status"] == "PASS"
    assert report["registry_source_path"] == registry_path.as_posix()


def test_m05_rejects_path_traversal_and_empty_policy():
    registry = _real_registry()
    registry["artifacts"][0]["path"] = "../outside.yaml"
    with pytest.raises(ValueError, match="path traversal"):
        _run(registry=registry)

    with pytest.raises(ValueError, match="formats must be non-empty"):
        _run(policy={"policy_id": "empty", "formats": {}, "forbidden": ["rule"]})


def test_m05_rejects_duplicate_registry_identity_and_path():
    registry = _real_registry()
    registry["artifacts"].append(deepcopy(registry["artifacts"][0]))
    registry["expected_artifact_count"] = len(registry["artifacts"])
    with pytest.raises(ValueError, match="artifact_id values must be unique"):
        _run(registry=registry)

    registry = _real_registry()
    registry["artifacts"][1]["path"] = registry["artifacts"][0]["path"]
    registry["artifacts"][1]["sha256"] = registry["artifacts"][0]["sha256"]
    with pytest.raises(ValueError, match="paths must be unique"):
        _run(registry=registry)


def test_m05_rejects_nested_forbidden_fields():
    registry = _real_registry()
    registry["metadata"] = {"nested": [{"target": "leak"}]}
    with pytest.raises(ValueError, match="forbidden input fields"):
        _run(registry=registry)


def test_m05_enforces_forbidden_raw_excel_contract_rule(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "REPOSITORY_ROOT", tmp_path)
    contract = tmp_path / "contracts" / "bad.xlsx"
    contract.parent.mkdir(parents=True)
    contract.write_text("not-an-excel-contract", encoding="utf-8")
    registry = _complete(
        [
            {
                "artifact_id": "bad-excel-contract",
                "artifact_type": "contract",
                "format": "yaml",
                "path": "contracts/bad.xlsx",
            }
        ]
    )
    policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    report = _run(registry=registry, policy=policy)
    assert "raw_excel_as_contract" in {item["code"] for item in report["findings"]}
    assert report["status"] == "BLOCKED"


def test_m05_rejects_policy_format_without_implemented_validator():
    policy = {
        "policy_id": "future-policy",
        "formats": {"contract": "toml"},
        "forbidden": ["pickle_for_cross_phase_artifacts"],
    }
    with pytest.raises(ValueError, match="formats without validators"):
        _run(policy=policy)
