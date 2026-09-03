from __future__ import annotations

import json

from .s31_support import run_m01, run_m02


def test_s31_end_to_end_export():
    bundle = run_m01()
    manifest = run_m02(bundle=bundle)
    assert manifest["bundle_artifact_id"] == bundle["artifact_id"]
    assert manifest["artifact_hashes"]["p9_evaluation_evidence_bundle"] == manifest["bundle_content_hash"]
    assert bundle["evaluation_authority"] == manifest["evaluation_authority"] == "P9"


def test_s31_outputs_are_byte_stable():
    first = {"bundle": run_m01()}
    first["manifest"] = run_m02(bundle=first["bundle"])
    second = {"bundle": run_m01()}
    second["manifest"] = run_m02(bundle=second["bundle"])
    assert json.dumps(first, sort_keys=True, separators=(",", ":")) == json.dumps(
        second, sort_keys=True, separators=(",", ":")
    )
