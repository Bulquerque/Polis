from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel


class CanonicalHasher(Protocol):
    def __call__(self, value: object) -> str: ...


def artifact_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    """Return a canonical artifact payload without identity/hash fields."""
    data = value.model_dump(mode="python") if isinstance(value, BaseModel) else dict(value)
    data.pop("artifact_id", None)
    data.pop("content_hash", None)
    return data


def compute_artifact_hash(
    value: BaseModel | dict[str, Any],
    *,
    hasher: CanonicalHasher,
) -> str:
    """Hash a canonical artifact payload using the capability's canonicalizer."""
    return hasher(artifact_payload(value))
