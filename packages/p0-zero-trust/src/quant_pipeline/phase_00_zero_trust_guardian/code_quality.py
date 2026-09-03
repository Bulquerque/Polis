from __future__ import annotations
from pathlib import Path

DEFAULT_MAX_LINES = 800

def detect_monoliths(root: str | Path, max_lines: int = DEFAULT_MAX_LINES) -> list[dict[str, int | str]]:
    root = Path(root)
    findings = []
    for p in root.rglob('*.py'):
        if '__pycache__' in p.parts:
            continue
        n = len(p.read_text(encoding='utf-8', errors='ignore').splitlines())
        if n > max_lines:
            findings.append({'path': str(p.relative_to(root)), 'line_count': n})
    return findings

def detect_duplicate_files(hash_manifest: list[dict[str, str | int]]) -> list[dict[str, object]]:
    by_hash: dict[str, list[str]] = {}
    for row in hash_manifest:
        by_hash.setdefault(str(row['sha256']), []).append(str(row['path']))
    return [{'sha256': h, 'paths': paths} for h, paths in by_hash.items() if len(paths) > 1]
