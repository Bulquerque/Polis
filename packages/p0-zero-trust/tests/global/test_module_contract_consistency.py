import json
from pathlib import Path
from tools.documentary_module_scope import documentary_status_paths


def workspace_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "GLOBAL_MODULE_TABLE.csv").exists():
            return candidate
    raise AssertionError("workspace root not found")


def test_module_contract_consistency_audit_has_no_drift():
    root = workspace_root()
    report = json.loads((root / "reports/documentation/module_contract_consistency_audit.json").read_text(encoding="utf-8"))
    expected = len(documentary_status_paths(root))
    assert report["module_count"] == expected
    assert report["consistency_pass_count"] == expected
    assert report["consistency_fail_count"] == 0
    assert report["pending_status_count"] == 0
    blocked = sum(
        json.loads(path.read_text(encoding="utf-8")).get("status", "").lower() == "blocked"
        for path in documentary_status_paths(root)
    )
    assert report["pass_status_count"] == expected - blocked
    assert report["blocked_status_count"] == blocked
    assert report["promotion_allowed"] is False
