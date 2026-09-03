"""Optional Redis-backed immutable byte store for P3 RAG artifacts.

Redis is an infrastructure adapter, not a replacement for the governed memory
state or its point-in-time policy.  The adapter therefore keeps the same
content-addressed and hash-verified semantics as the local stores and fails
explicitly when the optional dependency/server is unavailable.
"""

from __future__ import annotations

from typing import Any

from ..canonical import sha256_bytes
from ..models import ArtifactRef


class RedisArtifactStore:
    """Async Redis byte store; construct with an existing redis.asyncio client."""

    def __init__(self, client: Any, *, namespace: str = "p3:artifact") -> None:
        self._client = client
        self._namespace = namespace.rstrip(":")

    @classmethod
    def from_url(cls, url: str, *, namespace: str = "p3:artifact") -> "RedisArtifactStore":
        try:
            from redis import asyncio as redis_asyncio
        except ImportError as exc:
            raise RuntimeError("Redis adapter requires the optional 'redis' package") from exc
        return cls(redis_asyncio.from_url(url, decode_responses=False), namespace=namespace)

    def _key(self, artifact_type: str, digest: str) -> str:
        return f"{self._namespace}:{artifact_type}:{digest}"

    async def put_bytes(
        self,
        *,
        artifact_type: str,
        content: bytes,
        media_type: str,
        suffix: str,
        record_count: int | None,
        format_version: str,
    ) -> ArtifactRef:
        digest = sha256_bytes(content)
        key = self._key(artifact_type, digest)
        prior = await self._client.get(key)
        if prior is not None and bytes(prior) != content:
            raise ValueError("immutable Redis artifact collision")
        if prior is None:
            await self._client.set(key, content)
        return ArtifactRef(
            artifact_type=artifact_type,
            uri=f"redis://{key}{suffix}",
            content_hash=digest,
            media_type=media_type,
            size_bytes=len(content),
            record_count=record_count,
            format_version=format_version,
        )

    async def get_bytes(self, reference: ArtifactRef) -> bytes:
        key = reference.uri.removeprefix("redis://").split(".", 1)[0]
        content = await self._client.get(key)
        if content is None:
            raise KeyError(f"Redis artifact not found: {key}")
        content = bytes(content)
        if sha256_bytes(content) != reference.content_hash:
            raise ValueError("Redis artifact hash mismatch")
        return content

