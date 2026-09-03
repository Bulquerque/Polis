"""NVIDIA NIM URL normalization with no optional dependencies."""
from __future__ import annotations

from urllib.parse import urlsplit


def normalize_nvidia_nim_endpoint(base_url: str, operation: str = "chat/completions") -> str:
    """Return one canonical NIM endpoint from a base or endpoint URL."""
    value = base_url.strip().rstrip("/")
    if not value:
        raise ValueError("NVIDIA NIM base URL cannot be empty")
    suffix = f"/{operation.lstrip('/')}"
    if value.endswith(suffix):
        return value
    if urlsplit(value).path.rstrip("/").endswith("/v1"):
        return f"{value}{suffix}"
    return f"{value}/v1{suffix}"
