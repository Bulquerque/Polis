from __future__ import annotations

import ast
from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "quant_pipeline" / "phase_07_strategy_tournament"


def _functions(tree: ast.AST):
    return (node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)))


def test_single_sequential_layout_and_module_authority() -> None:
    assert not (SOURCE / "components").exists()
    assert not (SOURCE / "modules").exists()
    wrappers = sorted(SOURCE.rglob("modules/P7_*.py"))
    assert len(wrappers) == 33
    registry = yaml.safe_load((ROOT / "contracts" / "MODULE_REGISTRY.yaml").read_text())
    assert registry["module_count"] == 33
    assert len(registry["modules"]) == 33
    assert len({row["module_id"] for row in registry["modules"]}) == 33
    assert {str((ROOT / row["source_path"]).resolve()) for row in registry["modules"]} == {
        str(path.resolve()) for path in wrappers
    }


def test_no_parallel_origin_vocabulary_or_legacy_public_names() -> None:
    forbidden = ("ag" + "ent", "comp" + "onents/a", "un" + "ified")
    text_roots = (SOURCE, ROOT / "contracts", ROOT / "configs", ROOT / "README.md", ROOT / "ARCHITECTURE.md", ROOT / "SUBPHASES.md", ROOT / "MODULE_CATALOG.md", ROOT / "NAVIGATION.md", ROOT / "DEBUGGING_RUNBOOK.md")
    for item in text_roots:
        paths = [item] if item.is_file() else [p for p in item.rglob("*") if p.is_file() and p.suffix in {".py", ".md", ".yaml", ".yml", ".json", ".toml"}]
        for path in paths:
            text = path.read_text(errors="ignore").lower()
            assert all(token not in text for token in forbidden), path
            assert not re.search(r"\bA[1-4]\b", path.read_text(errors="ignore")), path
            assert not re.search(r"artifact_name[^\n]*_v2\b", text), path


def test_source_size_and_exception_limits() -> None:
    for path in SOURCE.rglob("*.py"):
        text = path.read_text()
        assert len(text.splitlines()) <= 350, path
        tree = ast.parse(text)
        for node in _functions(tree):
            assert node.end_lineno is not None
            assert node.end_lineno - node.lineno + 1 <= 60, (path, node.name)
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is not None:
                if isinstance(node.type, ast.Name):
                    assert node.type.id not in {"Exception", "BaseException"}, path
                if isinstance(node.type, ast.Tuple):
                    names = {elt.id for elt in node.type.elts if isinstance(elt, ast.Name)}
                    assert not names.intersection({"Exception", "BaseException"}), path
    for path in SOURCE.rglob("modules/P7_*.py"):
        assert len(path.read_text().splitlines()) <= 80, path


def test_no_fabricated_confidence_or_ood_defaults() -> None:
    text = "\n".join(path.read_text() for path in SOURCE.rglob("*.py"))
    forbidden_patterns = (
        r"data_quality_score\s*=\s*1\.0",
        r"ood_score\s*=\s*0\.0",
        r"score_confidence\s*=\s*1\.0",
        r"liquidity[^\n=]*=\s*1\.0",
        r"cost[^\n=]*=\s*0\.0",
    )
    for pattern in forbidden_patterns:
        assert re.search(pattern, text) is None, pattern


def test_local_error_hierarchies_share_the_phase_root() -> None:
    from quant_pipeline.phase_07_strategy_tournament.errors import P7Error
    from quant_pipeline.phase_07_strategy_tournament.foundation.errors import P7S1Error
    from quant_pipeline.phase_07_strategy_tournament.foundation.s2_errors import P7S2Error
    from quant_pipeline.phase_07_strategy_tournament.learning.domain.errors import P7LearningError
    from quant_pipeline.phase_07_strategy_tournament.tournament.domain.errors import P7TournamentError
    from quant_pipeline.phase_07_strategy_tournament.finalization.errors import P7Error as P7FinalizationError

    for error_type in (P7S1Error, P7S2Error, P7LearningError, P7TournamentError, P7FinalizationError):
        assert issubclass(error_type, P7Error)
