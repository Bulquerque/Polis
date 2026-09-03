"""Guarantee that generated P7 test snapshots match canonical sources."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests" / "SNAPSHOT_MANIFEST.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_generated_test_snapshots_match_canonical_sources() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert payload["authority"] == "canonical production contracts/configs/schemas"
    records = payload["records"]
    assert len(records) == payload["generated_snapshots"]
    assert len(records) >= 199
    for record in records:
        snapshot = ROOT / record["snapshot"]
        canonical = ROOT / record["canonical"]
        assert snapshot.is_file(), record["snapshot"]
        assert canonical.is_file(), record["canonical"]
        assert digest(canonical) == record["sha256"]
        assert snapshot.read_bytes() == canonical.read_bytes()
