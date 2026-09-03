from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import Field, field_validator, model_validator

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import ContractModel

from .types import CorpusMode, NonEmptyStr, aware_utc

QueryText = Annotated[str, Field(min_length=1, max_length=4000)]
ShortQueryText = Annotated[str, Field(min_length=1, max_length=1000)]


class CorpusToolCallContext(ContractModel):
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    request_id: NonEmptyStr
    cognition_transaction_id: NonEmptyStr
    person_id: NonEmptyStr
    decision_time: datetime
    deterministic_seed: int = Field(ge=0)

    _decision = field_validator("decision_time")(aware_utc)


class CorpusFilter(ContractModel):
    source_ids: tuple[NonEmptyStr, ...] = ()
    document_ids: tuple[NonEmptyStr, ...] = ()
    document_types: tuple[NonEmptyStr, ...] = ()
    entity_ids: tuple[NonEmptyStr, ...] = ()
    underlying_ids: tuple[NonEmptyStr, ...] = ()
    available_from: datetime | None = None
    available_to: datetime | None = None

    _from = field_validator("available_from")(aware_utc)
    _to = field_validator("available_to")(aware_utc)

    @model_validator(mode="after")
    def validate_interval_and_uniqueness(self) -> "CorpusFilter":
        if self.available_from and self.available_to and self.available_from > self.available_to:
            raise ValueError("available_from must not be after available_to")
        for field_name in (
            "source_ids",
            "document_ids",
            "document_types",
            "entity_ids",
            "underlying_ids",
        ):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must contain unique values")
        return self


class SearchCorpusRequest(ContractModel):
    query: QueryText
    filters: CorpusFilter = Field(default_factory=CorpusFilter)
    research_mode: CorpusMode = CorpusMode.LOOKUP
    max_results: int | None = Field(default=None, gt=0, le=100)


class GetDocumentRequest(ContractModel):
    document_id: NonEmptyStr
    include_content: bool = True
    research_mode: CorpusMode = CorpusMode.LOOKUP


class CompareVersionsRequest(ContractModel):
    left_document_id: NonEmptyStr
    right_document_id: NonEmptyStr
    research_mode: CorpusMode = CorpusMode.STANDARD

    @model_validator(mode="after")
    def distinct_documents(self) -> "CompareVersionsRequest":
        if self.left_document_id == self.right_document_id:
            raise ValueError("version comparison requires two different document IDs")
        return self


class InspectProvenanceRequest(ContractModel):
    document_id: NonEmptyStr | None = None
    chunk_id: NonEmptyStr | None = None
    research_mode: CorpusMode = CorpusMode.LOOKUP

    @model_validator(mode="after")
    def exactly_one_identifier(self) -> "InspectProvenanceRequest":
        if (self.document_id is None) == (self.chunk_id is None):
            raise ValueError("provide exactly one of document_id or chunk_id")
        return self


class FindCounterevidenceRequest(ContractModel):
    proposition: QueryText
    counter_queries: tuple[ShortQueryText, ...]
    filters: CorpusFilter = Field(default_factory=CorpusFilter)
    research_mode: CorpusMode = CorpusMode.TRIANGULATED
    max_results: int | None = Field(default=None, gt=0, le=100)

    @model_validator(mode="after")
    def validate_counter_queries(self) -> "FindCounterevidenceRequest":
        if not self.counter_queries:
            raise ValueError("counter_queries cannot be empty")
        if len(self.counter_queries) > 8:
            raise ValueError("counter_queries exceed the hard internal limit")
        if len(self.counter_queries) != len(set(self.counter_queries)):
            raise ValueError("counter_queries must be unique")
        return self


class BuildTimelineRequest(ContractModel):
    filters: CorpusFilter = Field(default_factory=CorpusFilter)
    query: str | None = Field(default=None, max_length=4000)
    research_mode: CorpusMode = CorpusMode.STANDARD
    max_events: int | None = Field(default=None, gt=0, le=200)

    @field_validator("query")
    @classmethod
    def non_blank_query(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("query must be non-blank when provided")
        return value
