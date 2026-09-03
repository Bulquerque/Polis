from __future__ import annotations

import ast
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "src/quant_pipeline/phase_03_agents_rag_memory"
EXTENSION = PACKAGE / "extensions/research_tools"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_extension_has_no_direct_legacy_or_workspace_addendum_imports() -> None:
    forbidden = (
        "extensions.p3_mcp_addendum",
        "quant_pipeline.phase_03_agents_rag_memory.modules.P3_S32",
        "quant_pipeline.phase_03_agents_rag_memory.modules.P3_S33",
        "quant_pipeline.phase_03_agents_rag_memory.modules.P3_S34",
        "quant_pipeline.phase_03_agents_rag_memory.modules.P3_S35",
        "quant_pipeline.phase_03_agents_rag_memory.modules.P3_S36",
        "quant_pipeline.phase_03_agents_rag_memory.modules.P3_S37",
        "quant_pipeline.phase_03_agents_rag_memory.modules.P3_S38",
        "quant_pipeline.phase_03_agents_rag_memory.modules.P3_S39",
        "quant_pipeline.phase_03_agents_rag_memory.modules.P3_S40",
    )
    for path in EXTENSION.rglob("*.py"):
        imports = _imported_modules(path)
        assert not any(
            imported == prefix or imported.startswith(f"{prefix}.")
            for imported in imports
            for prefix in forbidden
        ), path


def test_gateway_policy_projection_has_one_owner() -> None:
    occurrences: list[Path] = []
    pattern = re.compile(r"MCPGatewayPolicy\s*\.model_validate\s*\(")
    for path in EXTENSION.rglob("*.py"):
        if pattern.search(path.read_text(encoding="utf-8")):
            occurrences.append(path.relative_to(ROOT))
    assert occurrences == [
        Path("src/quant_pipeline/phase_03_agents_rag_memory/extensions/research_tools/compatibility/s21_gateway_policy.py")
    ]


def test_extension_registry_is_manifest_driven_not_hand_copied_into_legacy_registry() -> None:
    source = (PACKAGE / "orchestration/registry.py").read_text(encoding="utf-8")
    assert "extension_module_rows()" in source
    assert not re.search(r'module_id\s*=\s*["\']P3\.S3[2-9]', source)
    assert not re.search(r'module_id\s*=\s*["\']P3\.S40', source)


def test_external_mcp_is_explicitly_optional_and_disabled() -> None:
    config = yaml.safe_load(
        (ROOT / "config/research_tools/PROVIDER_TRANSPORT_BINDINGS.yaml").read_text(encoding="utf-8")
    )
    provider = next(item for item in config["providers"] if item["provider_id"] == "research_mcp")
    assert provider["transport"] == "MCP_OPTIONAL"
    assert provider["configured"] is False
    assert provider["qualified"] is False
