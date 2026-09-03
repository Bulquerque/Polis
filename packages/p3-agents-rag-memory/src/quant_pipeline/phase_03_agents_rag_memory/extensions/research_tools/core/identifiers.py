"""Identifier validation and normalization without hidden aliases."""

from __future__ import annotations

import re

TOOL_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\.v[1-9][0-9]*$")
OPERATION_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
MODE_ID_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
HANDLER_ID_RE = re.compile(r"^(?:internal|adapter)\.[a-z][a-z0-9_.]*$")
PROVIDER_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
MODULE_ID_RE = re.compile(r"^P3\.S(?:3[2-9]|40)\.M(?:0[1-9]|[1-9][0-9]*)$")


def require_match(value: str, pattern: re.Pattern[str], label: str) -> str:
    if not pattern.fullmatch(value):
        raise ValueError(f"invalid {label}: {value!r}")
    return value
