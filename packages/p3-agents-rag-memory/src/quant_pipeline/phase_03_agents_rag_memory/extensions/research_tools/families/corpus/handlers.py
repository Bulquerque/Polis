from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from pydantic import JsonValue

from .document_handlers import DocumentCorpusHandlers
from .errors import CorpusToolError, ErrorCategory, error
from .models import CorpusRetrievalPolicy, CorpusToolCallContext, CorpusToolResultEnvelope
from .ports import CorpusRepositoryPort, ProvenanceQueryPort, RawEvidenceResolverPort
from .provenance import DocumentAssembler, ProvenanceAssembler, VersionComparator
from .reasoning_handlers import ReasoningCorpusHandlers
from .retrieval import HybridCorpusRetriever

Handler = Callable[[Mapping[str, JsonValue], CorpusToolCallContext], Awaitable[CorpusToolResultEnvelope]]


@dataclass(frozen=True, slots=True)
class CorpusRuntimeHandlerBundle:
    handlers: Mapping[str, Handler]

    async def execute(
        self,
        operation_id: str,
        arguments: Mapping[str, JsonValue],
        context: CorpusToolCallContext,
    ) -> CorpusToolResultEnvelope:
        handler = self.handlers.get(operation_id)
        if handler is None:
            raise CorpusToolError(
                error(
                    "P3_RT_HANDLER_NOT_REGISTERED",
                    ErrorCategory.CONFIGURATION,
                    "corpus operation has no registered handler",
                    context={"operation_id": operation_id},
                )
            )
        return await handler(arguments, context)


class CorpusHandlers:
    def __init__(
        self,
        *,
        repository: CorpusRepositoryPort,
        retriever: HybridCorpusRetriever,
        policy: CorpusRetrievalPolicy,
        raw_resolver: RawEvidenceResolverPort | None = None,
        provenance_port: ProvenanceQueryPort | None = None,
    ) -> None:
        documents = DocumentAssembler(repository=repository, raw_resolver=raw_resolver)
        provenance = ProvenanceAssembler(
            repository=repository,
            provenance_port=provenance_port,
        )
        self._documents = DocumentCorpusHandlers(
            repository=repository,
            retriever=retriever,
            documents=documents,
            versions=VersionComparator(),
            provenance=provenance,
        )
        self._reasoning = ReasoningCorpusHandlers(
            repository=repository,
            retriever=retriever,
            policy=policy,
        )

    def bundle(self) -> CorpusRuntimeHandlerBundle:
        handlers = {
            "search": self._documents.search,
            "get_document": self._documents.get_document,
            "compare_versions": self._documents.compare_versions,
            "inspect_provenance": self._documents.inspect_provenance,
            "find_counterevidence": self._reasoning.find_counterevidence,
            "build_timeline": self._reasoning.build_timeline,
        }
        return CorpusRuntimeHandlerBundle(handlers=MappingProxyType(handlers))
