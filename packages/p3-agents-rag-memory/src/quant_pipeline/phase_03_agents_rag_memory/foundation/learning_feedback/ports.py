from __future__ import annotations
from typing import Any, Protocol
class CommitmentResolverPort(Protocol):
    def resolve(self, commitment_id:str) -> dict[str,Any]: ...
