from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json
import re
import zipfile

import yaml


PIPELINE_VERSION = "V14.1-RC4.1"
CREATED_AT = "2026-07-19T00:00:00Z"


class MaterialP0FixtureBuilder:
    """Build real phase inputs and preserve every runtime handoff unmodified."""

    def __init__(self, package_root: Path, scratch_root: Path):
        self.root = package_root.resolve()
        self.workspace = self.root.parents[1]
        self.global_root = self.workspace / "global_contracts_parallel_agents" / "v14_1_global_contracts_parallel_agents_RC4_1"
        self.scratch = scratch_root.resolve()
        self.scratch.mkdir(parents=True, exist_ok=True)
        self.config = {
            "pipeline_version": PIPELINE_VERSION,
            "created_at": CREATED_AT,
            "release_id": "P0-material-fixture",
            "release_scope": "P0_TECHNICAL_CLOSURE",
        }

    @staticmethod
    def _sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _contract_entries(self) -> list[dict[str, Any]]:
        registry = yaml.safe_load((self.global_root / "source_of_truth" / "registries" / "module_registry.yaml").read_text(encoding="utf-8"))
        modules = [item for item in registry["modules"] if item.get("phase_id") == "P0"]
        return [{"artifact_id": item["module_id"], "path": item["contract_path"], "sha256": self._sha(self.workspace / item["contract_path"]), "artifact_type": "contract", "format": "yaml"} for item in modules]

    @staticmethod
    def _pattern_value(pattern: str) -> str:
        known = {
            "^FF-[0-9]{4}$": "FF-0001", "^HC-[0-9]{6}$": "HC-000001", "^IM-[0-9]{5}$": "IM-00001", "^MA-[0-9]{6}$": "MA-000001",
            "^P[0-9]$": "P0", "^P[0-9]+$": "P0", "^P[0-9]+\\.S[0-9]+$": "P0.S1", "^P[0-9]+\\.S[0-9]+\\.M[0-9]+$": "P0.S1.M01",
            "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$": CREATED_AT,
            "^[0-9a-f]{40}$": "a" * 40, "^[0-9a-f]{64}$": "a" * 64, "^sha256:[0-9a-f]{64}$": "sha256:" + "a" * 64,
            "^modules/P[0-9]+_S[0-9]+_M[0-9]+_[A-Za-z0-9_]+\\.yaml$": "modules/P0_S1_M01_fixture.yaml",
        }
        if pattern in known:
            return known[pattern]
        match = re.fullmatch(r"\^([a-z-]+)-\[0-9a-f\]\{12\}\$", pattern)
        if match:
            return match.group(1) + "-" + "a" * 12
        raise AssertionError(f"fixture generator lacks pattern sample: {pattern}")

    @classmethod
    def _valid_value(cls, schema: dict[str, Any], field: str = "value") -> Any:
        if "const" in schema:
            return schema["const"]
        if schema.get("enum"):
            return schema["enum"][0]
        kind = schema.get("type", "object" if schema.get("required_fields") or schema.get("required") else "string")
        if kind == "object":
            properties = schema.get("properties", {}) if isinstance(schema.get("properties", {}), dict) else {}
            required = schema.get("required_fields", schema.get("required", []))
            result = {name: cls._valid_value(properties.get(name, {}), name) for name in required}
            min_properties = max(0, int(schema.get("minProperties", 0)))
            if len(result) < min_properties:
                additional = schema.get("additionalProperties")
                additional_schema = additional if isinstance(additional, dict) else {}
                index = 1
                while len(result) < min_properties:
                    key = f"property_{index}"
                    index += 1
                    if key in result:
                        continue
                    result[key] = cls._valid_value(additional_schema, key)
            return result
        if kind == "array":
            return [cls._valid_value(schema.get("items", {}), field) for _ in range(max(0, int(schema.get("minItems", 0))))]
        if kind == "integer": return int(schema.get("minimum", 0))
        if kind == "number": return float(schema.get("minimum", 0))
        if kind == "boolean": return True
        if schema.get("pattern"): return cls._pattern_value(str(schema["pattern"]))
        return (field or "value")[: max(1, int(schema.get("minLength", 1)))] or "x"

    def schema_fixtures(self) -> dict[str, Any]:
        fixtures = []
        for path in sorted(self.global_root.rglob("*.schema.yaml")):
            schema = yaml.safe_load(path.read_text(encoding="utf-8"))
            artifact_name = schema.get("artifact_name") or schema.get("artifact") or path.name.removesuffix(".schema.yaml")
            schema_id = schema.get("schema_id") or f"{artifact_name}.v1"
            fixtures.append({"fixture_id": f"{schema_id}:valid", "schema_id": schema_id, "expectation": "valid", "payload": self._valid_value(schema)})
            fixtures.append({"fixture_id": f"{schema_id}:invalid", "schema_id": schema_id, "expectation": "invalid", "payload": {}})
        return {"fixtures": fixtures}

    @staticmethod
    def _test_reports(family: str) -> dict[str, Any]:
        return {"reports": [{"test_run_id": f"{family}-P{i}", "phase_id": f"P{i}", "total_tests": 1, "passed_tests": 1, "failed_tests": 0, "skipped_tests": 0, "status": "PASS"} for i in range(10)]}

    def _agent_zip(self) -> str:
        path = self.scratch / "agent-package.zip"
        with zipfile.ZipFile(path, "w") as archive:
            files = (("SKILL.md", "# Material audit skill\n"), ("tests/test_skill.py", "def test_material_skill():\n    assert True\n"))
            for name, content in files:
                info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, content)
            manifest_info = zipfile.ZipInfo("agent_manifest.json", (2026, 1, 1, 0, 0, 0))
            manifest_info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(manifest_info, json.dumps({
                "execution_policy_id": "p0-s7-agent-governance",
                "files": [{"path": name, "sha256": hashlib.sha256(content.encode()).hexdigest()} for name, content in files],
            }, sort_keys=True))
        return path.name

    def external_inputs(self) -> dict[str, Any]:
        contracts = self._contract_entries()
        manifest = {"artifacts": [{"path": item["path"], "sha256": item["sha256"], "artifact_id": item["artifact_id"]} for item in contracts]}
        registry = {"inventory_scope": "all_phase_artifacts", "inventory_complete": True, "expected_artifact_count": len(contracts), "artifacts": contracts}
        source = {"files": [{"path": "fixtures/material_source.py", "size_bytes": 24, "content": "def material():\n    return 1\n"}]}
        file_hashes = {"entries": [{"path": "fixtures/material_source.py", "sha256": hashlib.sha256(source["files"][0]["content"].encode()).hexdigest()}]}
        module_ids = [item["artifact_id"] for item in contracts]
        phases = [{"artifact_id": f"dashboard-P{i}", "phase_id": f"P{i}", "lineage_id": "sha256:" + f"{i:x}" * 64, "status": "PASS", "release_blocking": False, "findings": []} for i in range(10)]
        development_state = {
            "phases": {
                "P0": {
                    "development_status": "IMPLEMENTED",
                    "documentation_status": "READY",
                    "module_counts": {"planned": 40, "implemented": 40, "tested": 40, "qualified": 0},
                },
                **{
                    f"P{i}": {
                        "development_status": "NOT_STARTED",
                        "documentation_status": "READY",
                        "module_counts": {"planned": 0, "implemented": 0, "tested": 0, "qualified": 0},
                    }
                    for i in range(1, 10)
                },
            }
        }
        qualification_state = {
            "phases": {
                "P0": {"qualification_status": "QUALIFICATION_RUNNING"},
                **{f"P{i}": {"qualification_status": "NOT_ELIGIBLE"} for i in range(1, 10)},
            }
        }
        previous = {"artifact_id": "previous-release", "pipeline_version": "V14.1-RC4.0", "lineage_id": "sha256:" + "b" * 64, "status": "PASS", "release_blocking": False, "release_id": "RC4.0", **manifest}
        matrices = [yaml.safe_load(path.read_text(encoding="utf-8")) for path in sorted(self.workspace.glob("phase_00_zero_trust/**/contracts/MODULE_IO_MATRIX.yaml"))]
        return {
            "phase_registry_yaml": str(self.root / "source_of_truth" / "registries" / "phase_registry.yaml"),
            "global_architecture_config": {"authority": "global_master", "pipeline_version": PIPELINE_VERSION, "phase_registry_id": "phase_registry_v14_1_rc4_1"},
            "subphase_registry_yaml": str(self.root / "source_of_truth" / "registries" / "subphase_registry.yaml"),
            "module_registry_yaml": str(self.root / "source_of_truth" / "registries" / "module_registry.yaml"),
            "connection_matrix_yaml": str(self.root / "contracts" / "MODULE_IO_MATRIX.yaml"),
            "forbidden_connection_matrix_yaml": str(self.root / "contracts" / "CONNECTIONS.yaml"),
            "module_io_matrix_all_phases": matrices,
            "contracts_all_phases": str(self.global_root / "source_of_truth" / "registries" / "module_registry.yaml"),
            "global_contracts": str(self.global_root / "contracts"),
            "schemas_all_phases": [str(path) for path in sorted(self.workspace.glob("global_contracts_parallel_agents/**/*.schema.yaml")) + sorted(self.workspace.glob("phase_*/**/*.schema.yaml"))],
            "artifact_registry": registry,
            "artifact_format_policy_yaml": str(self.global_root / "source_of_truth" / "standards" / "ARTIFACT_FORMAT_POLICY.yaml"),
            "forbidden_fields_yaml": {"forbidden_fields": ["future_return", "target", "candidate_score", "rank_score", "portfolio_weight", "realized_pnl", "trade_decision"]},
            "artifact_manifest_all_phases": manifest,
            "manifesto_all_packages": manifest,
            "hash_policy_yaml": {"algorithm": "sha256", "fail_on": ["missing_hash", "hash_mismatch"]},
            "hash_history": {"history_id": "material-history", "entries": [dict(item) for item in manifest["artifacts"]]},
            "release_manifest_previous": previous,
            "source_tree_manifest": source,
            "file_hash_manifest": file_hashes,
            "code_quality_policy_yaml": {"max_file_lines": 100, "max_function_lines": 50, "allowed_module_globals": []},
            "forbidden_import_policy_yaml": {"forbidden_imports": ["phase_09.*", "dashboard.business_logic"]},
            "modules_yaml_all_phases": {"entries": [{"module_id": mid, "path": f"modules/{mid}.yaml"} for mid in module_ids]},
            "tests_all_phases": {"entries": [{"module_id": mid, "path": f"tests/{mid}.py"} for mid in module_ids]},
            "test_run_report_all_phases": self._test_reports("run"),
            "contract_test_report_all_phases": self._test_reports("contract"),
            "schema_test_report_all_phases": self._test_reports("schema"),
            "code_quality_test_report_all_phases": self._test_reports("quality"),
            "fixtures_all_phases": self.schema_fixtures(),
            "dashboard_phase_payload_all_phases": {
                "phases": phases,
                "development_state_snapshot": development_state,
                "qualification_state_snapshot": qualification_state,
            },
            "agent_skill_definitions_yaml": {"skills": [{"skill_id": "audit", "phase_scope": "P0", "module_scope": ["P0.S7.M01"], "permissions": ["read"], "allowed_paths": ["reports/"]}]},
            "agent_prompt_templates": {"templates": [{"template_id": "audit-v1", "skill_id": "audit", "phase_scope": "P0", "system_prompt": "Audit only inside the approved P0 scope."}]},
            "zero_trust_rules": {"denied_directives": ["ignore global contract", "bypass gate"]},
            "code_standards": {"definition_of_done": ["tests pass", "evidence recorded"], "permissions": {"read": True, "write": False}},
            "testing_standards": {"required_tests": ["unit", "adversarial"], "required_package_files": ["SKILL.md", "tests/test_skill.py"]},
            "agent_phase_package_zip": self._agent_zip(),
        }
