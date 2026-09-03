from __future__ import annotations

from .handlers import CorpusHandlers, CorpusRuntimeHandlerBundle
from .models import CorpusIndexSnapshot, CorpusRetrievalPolicy
from .ports import (
    CorpusRepositoryPort,
    DenseRetrievalPort,
    ProvenanceQueryPort,
    RawEvidenceResolverPort,
    RerankerPort,
)
from .retrieval import HybridCorpusRetriever


def create_corpus_runtime_bundle(
    *,
    repository: CorpusRepositoryPort,
    snapshot: CorpusIndexSnapshot,
    policy: CorpusRetrievalPolicy,
    dense_retriever: DenseRetrievalPort | None = None,
    reranker: RerankerPort | None = None,
    raw_resolver: RawEvidenceResolverPort | None = None,
    provenance_port: ProvenanceQueryPort | None = None,
) -> CorpusRuntimeHandlerBundle:
    retriever = HybridCorpusRetriever(
        repository=repository,
        snapshot=snapshot,
        policy=policy,
        dense_retriever=dense_retriever,
        reranker=reranker,
    )
    return CorpusHandlers(
        repository=repository,
        retriever=retriever,
        policy=policy,
        raw_resolver=raw_resolver,
        provenance_port=provenance_port,
    ).bundle()
