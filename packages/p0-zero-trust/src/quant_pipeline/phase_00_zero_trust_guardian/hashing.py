from __future__ import annotations
from pathlib import Path
import hashlib

def sha256_file(path: str | Path) -> str:
    p = Path(path)
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def build_hash_manifest(root: str | Path) -> list[dict[str, str | int]]:
    root = Path(root)
    rows = []
    for p in sorted(root.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts and p.suffix != '.pyc':
            rows.append({'path': str(p.relative_to(root)), 'size_bytes': p.stat().st_size, 'sha256': sha256_file(p)})
    return rows
