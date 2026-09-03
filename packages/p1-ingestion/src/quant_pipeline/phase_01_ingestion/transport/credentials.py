from __future__ import annotations

import os
from typing import Mapping


class CredentialResolutionError(RuntimeError):
    pass


class CredentialResolver:
    """Resolve credential handles at runtime without persisting materialized values."""

    def __init__(self, environ: Mapping[str, str] | None = None):
        self._environ = environ if environ is not None else os.environ

    def resolve(self, handle: str | None, *, required: bool = False) -> str | None:
        if not handle:
            if required:
                raise CredentialResolutionError("credential handle is required")
            return None
        value = self._environ.get(handle)
        if required and not value:
            raise CredentialResolutionError(f"credential handle is not configured: {handle}")
        return value
