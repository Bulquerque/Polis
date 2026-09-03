from __future__ import annotations

from typing import Protocol, Sequence

from .models import OpenFigiJobResult, OpenFigiMappingJob


class ExternalIdentifierResolverPort(Protocol):
    async def map_jobs(
        self,
        jobs: Sequence[OpenFigiMappingJob],
    ) -> tuple[OpenFigiJobResult, ...]:
        """Map external identifiers without choosing an ambiguous candidate."""
