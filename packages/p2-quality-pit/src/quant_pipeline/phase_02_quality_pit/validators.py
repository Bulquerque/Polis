from __future__ import annotations

from . import fail_fast


def validate_no_forbidden_fields(columns: set[str], forbidden: set[str]) -> None:
    overlap = columns.intersection(forbidden)
    fail_fast(not overlap, f'forbidden fields detected: {sorted(overlap)}')
