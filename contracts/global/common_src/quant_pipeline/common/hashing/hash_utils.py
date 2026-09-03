from __future__ import annotations
from pathlib import Path
import hashlib


def compute_sha256(path: str | Path) -> str:
    # Compute SHA-256 for a file using streaming reads.
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"Cannot hash missing file: {p}")
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()
