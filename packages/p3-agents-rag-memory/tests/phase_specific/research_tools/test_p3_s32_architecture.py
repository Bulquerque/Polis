from __future__ import annotations

import ast
from pathlib import Path

from .support import ROOT


def test_extension_does_not_import_old_module_wrappers_or_network_clients():
    source_root = ROOT / "src/quant_pipeline/phase_03_agents_rag_memory/extensions/research_tools"
    forbidden = (".modules", "requests", "httpx", "aiohttp", "urllib.request")
    for path in source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            assert not any(any(token in name for token in forbidden) for name in names), path


def test_no_s41_references_in_new_extension():
    roots = [
        ROOT / "src/quant_pipeline/phase_03_agents_rag_memory/extensions/research_tools",
        ROOT / "config/research_tools",
        ROOT / "contracts/extensions/research_tools",
        ROOT / "subphases/extensions/research_tools/P3_S32_research_tool_contract_compatibility_foundation.md",
    ]
    for root in roots:
        paths = [root] if root.is_file() else list(root.rglob("*"))
        for path in paths:
            if path.is_file():
                assert "P3.S41" not in path.read_text(encoding="utf-8", errors="ignore")
