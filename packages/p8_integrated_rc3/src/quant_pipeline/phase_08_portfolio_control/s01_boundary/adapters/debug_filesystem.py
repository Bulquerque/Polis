"""Atomic file-system writer for sanitized S1 failure bundles."""

from __future__ import annotations

import os
from pathlib import Path

from quant_pipeline.phase_08_contracts.canonical import canonical_json_bytes, canonical_sha256

from ..debug import S1FailureDebugBundle


class FileDebugBundleWriter:
    def __init__(self, root: Path) -> None:
        self._root = root

    def write_failure(self, bundle: S1FailureDebugBundle) -> str:
        self._root.mkdir(parents=True, exist_ok=True)
        digest = canonical_sha256(bundle)
        final_path = self._root / f"{bundle.module_id.replace('.', '_')}_{digest[:16]}.json"
        temporary_path = final_path.with_suffix(".tmp")
        temporary_path.write_bytes(canonical_json_bytes(bundle))
        os.replace(temporary_path, final_path)
        return str(final_path)
