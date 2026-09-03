from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from pydantic import JsonValue
from quant_pipeline.phase_03_agents_rag_memory.contracts.base import content_hash


class InMemoryCompanyPort:
    def __init__(self):
        self.views = {
            "company_profile": (
                self.row("profile-old", "2024-01-01T00:00:00Z", entity_id="E1", legal_name="Old Co", effective_from="2020-01-01"),
                self.row("profile-future", "2025-01-01T00:00:00Z", entity_id="E1", legal_name="Future Co", effective_from="2025-01-01"),
            ),
            "financial_statements": (
                self.row("rev-original", "2024-02-01T00:00:00Z", entity_id="E1", statement_type="INCOME", concept_id="revenue", value=100.0, period_end="2023-12-31", filing_id="F1", filing_version="1"),
                self.row("op-original", "2024-02-01T00:00:00Z", entity_id="E1", statement_type="INCOME", concept_id="operating_income", value=20.0, period_end="2023-12-31", filing_id="F1", filing_version="1"),
                self.row("ni-original", "2024-02-01T00:00:00Z", entity_id="E1", statement_type="INCOME", concept_id="net_income", value=10.0, period_end="2023-12-31", filing_id="F1", filing_version="1"),
                self.row("ocf-original", "2024-02-01T00:00:00Z", entity_id="E1", statement_type="CASH_FLOW", concept_id="operating_cash_flow", value=12.0, period_end="2023-12-31", filing_id="F1", filing_version="1"),
                self.row("rev-restated", "2024-06-01T00:00:00Z", entity_id="E1", statement_type="INCOME", concept_id="revenue", value=95.0, period_end="2023-12-31", filing_id="F1R", filing_version="2", restates_filing_id="F1"),
            ),
            "company_guidance": (self.row("g1", "2024-03-01T00:00:00Z", entity_id="E1", metric="revenue", lower=105.0, upper=115.0),),
            "company_peers": (self.row("p1", "2024-01-15T00:00:00Z", entity_id="E1", peer_entity_id="E2", authority_class="DOCUMENTED"),),
            "corporate_actions": (self.row("d1", "2024-03-10T00:00:00Z", entity_id="E1", action_type="DIVIDEND", amount=2.0),),
        }

    @staticmethod
    def row(record_id, available_at, **extra):
        data={"record_id":record_id,"source_id":"fixture-company","artifact_id":"company-artifact","available_at":available_at,"source_quality":0.95,**extra}
        data["content_hash"]=content_hash(data)
        return data

    async def query(self, *, view_id: str, filters: Mapping[str, JsonValue], decision_time: datetime) -> Sequence[Mapping[str, JsonValue]]:
        del decision_time
        entity_id=filters.get("entity_id")
        return tuple(row for row in self.views.get(view_id, ()) if entity_id is None or row.get("entity_id")==entity_id)
