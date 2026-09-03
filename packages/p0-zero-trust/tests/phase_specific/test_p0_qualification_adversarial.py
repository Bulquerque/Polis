from __future__ import annotations

import io
import json
import stat
import zipfile

import pytest

from quant_pipeline.phase_00_zero_trust_guardian import runner
from quant_pipeline.phase_00_zero_trust_guardian.modules._p0_s7_package import inspect_package, validate_manifest


@pytest.mark.parametrize("field", ["target", "Target", "TARGET", "TaRgEt", "ＴＡＲＧＥＴ"])
def test_forbidden_fields_use_nfkc_casefold(field: str) -> None:
    assert runner._forbidden_paths({field: 1}, {"target"}) == [field]


@pytest.mark.parametrize(
    ("schema", "value"),
    [
        ({"const": 1}, 2), ({"minimum": 2}, 1), ({"maximum": 2}, 3),
        ({"minItems": 2}, [1]), ({"maxItems": 1}, [1, 2]),
        ({"uniqueItems": True}, [1, 1]),
        ({"type": "object", "properties": {"a": {}}, "additionalProperties": False}, {"a": 1, "b": 2}),
        ({"allOf": [{"minimum": 0}, {"maximum": 1}]}, 2),
        ({"anyOf": [{"const": 1}, {"const": 2}]}, 3),
        ({"oneOf": [{"type": "number"}, {"minimum": 0}]}, 1),
        ({"not": {"const": 1}}, 1), ({"enum": [1, 2]}, 3),
    ],
)
def test_schema_keywords_reject_invalid_values(schema: dict, value: object) -> None:
    with pytest.raises(ValueError):
        runner._validate_structure(value, schema, "value")


def _zip(entries: list[tuple[str, bytes, int]]) -> io.BytesIO:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data, mode in entries:
            info = zipfile.ZipInfo(name)
            info.external_attr = mode << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    buffer.seek(0)
    return buffer


def test_zip_bomb_is_rejected_during_central_directory_preflight() -> None:
    package = _zip([("pkg/bomb.py", b"0" * (2 * 1024 * 1024), stat.S_IFREG | 0o644)])
    entries, findings, manifest = inspect_package(package, {"package_limits": {"max_compression_ratio": 20}})
    assert entries == [] and manifest is None
    assert "COMPRESSION_RATIO_EXCEEDED" in {row["reason_code"] for row in findings}


def test_zip_symlink_is_rejected_from_metadata() -> None:
    package = _zip([("pkg/link.py", b"target", stat.S_IFLNK | 0o777)])
    entries, findings, _ = inspect_package(package, {})
    assert entries == []
    assert "SYMLINK_ENTRY" in {row["reason_code"] for row in findings}


def test_manifest_rejects_unlisted_executable() -> None:
    payload = b"print('x')\n"
    manifest = {"execution_policy_id": "p", "files": []}
    findings = validate_manifest(manifest, {"policy_id": "p", "require_agent_manifest": True}, [{"path": "pkg/extra.py", "sha256": __import__("hashlib").sha256(payload).hexdigest()}])
    assert "UNLISTED_ZIP_ENTRY" in {row["reason_code"] for row in findings}


def test_manifest_is_required() -> None:
    assert validate_manifest(None, {"require_agent_manifest": True}, [])[0]["reason_code"] == "AGENT_MANIFEST_MISSING"
