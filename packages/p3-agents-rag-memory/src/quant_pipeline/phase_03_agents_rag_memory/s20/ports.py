from __future__ import annotations
from typing import Protocol
from .models import (
    GraphArtifact,
    GraphConfig,
    IndexedItem,
    QueryPanel,
    RetrievalBundle,
    RetrievalQuery,
)

class MemoryPort(Protocol):

    def search(self, query: RetrievalQuery, *, top_k: int) -> tuple[IndexedItem, ...]:
        ...

class KnowledgePort(Protocol):

    def search(self, query: RetrievalQuery, *, top_k: int) -> tuple[IndexedItem, ...]:
        ...

class RerankerPort(Protocol):

    @property
    def ref(self) -> str:
        ...

    def rank(self, query: str, passages: tuple[str, ...]) -> tuple[float, ...]:
        ...


class GraphQueryPort(Protocol):

    @property
    def ref(self) -> str:
        ...

    def query(
        self,
        queries: QueryPanel,
        graph: GraphArtifact,
        config: GraphConfig,
        *,
        top_k: int,
    ) -> RetrievalBundle:
        ...

class TokenizerPort(Protocol):

    @property
    def ref(self) -> str:
        ...

    def count(self, text: str) -> int:
        ...
