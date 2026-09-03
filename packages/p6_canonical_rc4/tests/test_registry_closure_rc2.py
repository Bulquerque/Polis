from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_all_module_constants_match_canonical_registry() -> None:
    registry = yaml.safe_load((ROOT / "contracts" / "MODULE_REGISTRY.yaml").read_text())
    mismatches = []
    for row in registry["modules"]:
        path = ROOT / row["path"]
        text = path.read_text()
        match = re.search(r'^MODULE_ID\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        if match and match.group(1) != row["module_id"]:
            mismatches.append((row["module_id"], match.group(1), str(path)))
    assert mismatches == []


def test_reserved_generators_are_not_declared_operational() -> None:
    registry = yaml.safe_load((ROOT / "contracts" / "MODULE_REGISTRY.yaml").read_text())
    by_id = {row["module_id"]: row for row in registry["modules"]}
    assert by_id["P6.S3.M05"]["status"] == "RESERVED_CAPABILITY"
    assert by_id["P6.S3.M06"]["status"] == "RESERVED_CAPABILITY"
