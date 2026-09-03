import json
from pathlib import Path
from tools.documentary_module_scope import documentary_status_paths


def workspace_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "GLOBAL_MODULE_TABLE.csv").exists():
            return candidate
    raise AssertionError("workspace root not found")


def test_module_runtime_smoke_audit_is_complete_without_promotion():
    root = workspace_root()
    report = json.loads((root / "reports/documentation/module_runtime_smoke_audit.json").read_text(encoding="utf-8"))
    expected = len(documentary_status_paths(root))
    assert report["module_count"] == expected
    assert report["smoke_pass_count"] == 0
    assert report["positive_smoke_pass_count"] == 0
    assert report["fail_closed_pass_count"] + report["positive_smoke_pass_count"] == expected
    assert report["non_failing_outcome_count"] == expected
    assert report["smoke_fail_count"] == 0
    assert report["promotion_allowed"] is False
