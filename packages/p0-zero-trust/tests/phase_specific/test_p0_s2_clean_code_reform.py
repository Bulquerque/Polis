from pathlib import Path
import ast


ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = ROOT / "src" / "quant_pipeline" / "phase_00_zero_trust_guardian" / "modules"


def _reform_files():
    return sorted(MODULE_ROOT.glob("P0_S2_M*.py")) + sorted(MODULE_ROOT.glob("_s2_*.py"))


def test_s2_reform_respects_file_and_function_size_policy():
    for path in _reform_files():
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) <= 350, f"{path.name} has {len(lines)} lines"
        tree = ast.parse("\n".join(lines), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                length = node.end_lineno - node.lineno + 1
                assert length <= 60, f"{path.name}:{node.name} has {length} lines"


def test_s2_does_not_import_private_helpers_from_s1():
    for path in _reform_files():
        source = path.read_text(encoding="utf-8")
        assert "P0_S1_" not in source


def test_release_specific_counts_and_format_policy_are_not_hardcoded_in_public_modules():
    public = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(MODULE_ROOT.glob("P0_S2_M*.py"))
    )
    assert "EXPECTED_CONTRACT_COUNT" not in public
    assert "EXPECTED_GLOBAL_CONTRACT_COUNT" not in public
    assert "EXPECTED_SCHEMA_VERSION" not in public
    assert "SUPPORTED_FORMATS" not in public
