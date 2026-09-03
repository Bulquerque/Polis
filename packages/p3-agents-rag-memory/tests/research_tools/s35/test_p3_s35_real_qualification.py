from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))
sys.path.insert(0, str(PACKAGE_ROOT))

from tools.research_tools.s35 import qualify_p3_s35_real as s35  # noqa: E402


def _signed(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    declared = payload.pop("content_hash", None)
    assert isinstance(declared, str)
    assert s35.content_hash(payload) == declared
    payload["content_hash"] = declared
    return payload


def test_receipt_is_signed_and_has_exact_18_cells() -> None:
    receipt = _signed(s35.S35_RECEIPT)
    assert receipt["qualification_status"] == "QUALIFIED_LOCAL"
    assert receipt["capability_100_percent"] is True
    assert receipt["fixture_used"] is False
    assert receipt["mcp_used"] is False
    assert receipt["residual_blockers"] == []
    records = receipt["records"]
    assert isinstance(records, list)
    assert len(records) == 18
    assert all(item["status"] == "QUALIFIED_LOCAL" for item in records)
    assert len({(item["operation_id"], item["mode_id"]) for item in records}) == 18
    assert receipt["corpus_operation_mode_qualification"]["matrix_hash"] == receipt["operation_mode_qualification"]["matrix_hash"]


def test_all_signed_reports_and_source_bytes_are_verifiable() -> None:
    _signed(s35.S35_CAPTURE)
    _signed(s35.S35_SNAPSHOT)
    _signed(s35.S35_AUDIT)
    receipt = _signed(s35.S35_RECEIPT)
    for document_id, path_value in receipt["source_artifact_paths"].items():
        assert hashlib.sha256(Path(path_value).read_bytes()).hexdigest() == receipt["source_hashes"][document_id]


def test_version_graph_uses_two_real_ordered_revisions() -> None:
    capture = _signed(s35.S35_CAPTURE)
    revisions = capture["artifacts"]
    assert len(revisions) == 2
    assert all(item["provider"] == "wikipedia" for item in revisions)
    assert revisions[1]["parent_revision_id"] == revisions[0]["revision_id"]
    assert revisions[0]["available_at"] < revisions[1]["available_at"]
    for item in revisions:
        assert hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest() == item["content_hash"]


def test_runtime_rejects_future_decision_and_tampered_index() -> None:
    sources = s35._sec_artifacts() + s35._wiki_revisions()
    bundle, runtime = s35._build_runtime(sources)

    async def run_future() -> None:
        try:
            await bundle.execute(
                "search",
                {"query": "Apple", "research_mode": "LOOKUP"},
                s35._context("LOOKUP", "future").model_copy(update={"decision_time": s35.DECISION_TIME.replace(year=2027)}),
            )
        except Exception:
            return
        raise AssertionError("future decision_time was accepted")

    asyncio.run(run_future())
    bad_store = s35._ArtifactStore({
        runtime["chunk_uri"]: runtime["chunk_bytes"] + b"tamper",
        runtime["keyword_uri"]: runtime["keyword_bytes"],
    })
    try:
        s35.CorpusSnapshotIndexLoader(bad_store).load(
            retrieval_manifest=runtime["manifest"],
            phase3_run_snapshot={"snapshot_id": s35.SNAPSHOT_ID, "as_of": s35.DECISION_TIME},
        )
    except Exception:
        pass
    else:
        raise AssertionError("tampered chunk catalog was accepted")
