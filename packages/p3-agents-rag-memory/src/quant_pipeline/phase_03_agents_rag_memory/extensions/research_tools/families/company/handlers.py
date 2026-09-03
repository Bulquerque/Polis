"""Explicit handler bindings and process-local factory for P3.S38."""
from __future__ import annotations

from dataclasses import dataclass

from .analysis_handlers import GetCapitalAllocationHandler, GetFundamentalSnapshotHandler
from .model_base import CompanyMode, ExtensionLineage
from .models import HandlerBindingSpec, HandlerBundleManifest, hashed_payload
from .ports import PitResearchQueryPort
from .profile_handlers import GetGuidanceHandler, GetPeersHandler, GetProfileHandler
from .statement_handlers import GetFinancialStatementsHandler
from .valuation_handlers import CalculateValuationHandler

_RESULT_SCHEMA = "extensions/research_tools/schemas/company/company_operation_result.schema.json"
_ALL_MODES = tuple(CompanyMode)

PROFILE_BINDINGS = (
    HandlerBindingSpec(
        operation_id="get_profile", handler_id="company.get_profile.v1", handler_version="1.0.0",
        request_schema_ref="extensions/research_tools/schemas/company/get_profile_request.schema.json",
        result_schema_ref=_RESULT_SCHEMA, supported_modes=_ALL_MODES, required_view_ids=("company_profile",),
    ),
)
STATEMENT_BINDINGS = (
    HandlerBindingSpec(
        operation_id="get_financial_statements", handler_id="company.get_financial_statements.v1",
        handler_version="1.0.0",
        request_schema_ref="extensions/research_tools/schemas/company/get_financial_statements_request.schema.json",
        result_schema_ref=_RESULT_SCHEMA, supported_modes=_ALL_MODES, required_view_ids=("financial_statements",),
    ),
)
ANALYSIS_BINDINGS = (
    HandlerBindingSpec(
        operation_id="get_fundamental_snapshot", handler_id="company.get_fundamental_snapshot.v1",
        handler_version="1.0.0",
        request_schema_ref="extensions/research_tools/schemas/company/get_fundamental_snapshot_request.schema.json",
        result_schema_ref=_RESULT_SCHEMA, supported_modes=_ALL_MODES, required_view_ids=("financial_statements",),
    ),
    HandlerBindingSpec(
        operation_id="get_capital_allocation", handler_id="company.get_capital_allocation.v1",
        handler_version="1.0.0",
        request_schema_ref="extensions/research_tools/schemas/company/get_capital_allocation_request.schema.json",
        result_schema_ref=_RESULT_SCHEMA, supported_modes=_ALL_MODES,
        required_view_ids=("financial_statements", "corporate_actions"),
    ),
)
GUIDANCE_PEER_VALUATION_BINDINGS = (
    HandlerBindingSpec(
        operation_id="get_guidance", handler_id="company.get_guidance.v1", handler_version="1.0.0",
        request_schema_ref="extensions/research_tools/schemas/company/get_guidance_request.schema.json",
        result_schema_ref=_RESULT_SCHEMA, supported_modes=_ALL_MODES, required_view_ids=("company_guidance",),
    ),
    HandlerBindingSpec(
        operation_id="get_peers", handler_id="company.get_peers.v1", handler_version="1.0.0",
        request_schema_ref="extensions/research_tools/schemas/company/get_peers_request.schema.json",
        result_schema_ref=_RESULT_SCHEMA, supported_modes=_ALL_MODES, required_view_ids=("company_peers",),
    ),
    HandlerBindingSpec(
        operation_id="calculate_valuation", handler_id="company.calculate_valuation.v1",
        handler_version="1.0.0",
        request_schema_ref="extensions/research_tools/schemas/company/calculate_valuation_request.schema.json",
        result_schema_ref=_RESULT_SCHEMA, supported_modes=(CompanyMode.QUICK_CHECK, CompanyMode.STANDARD_REVIEW),
        required_view_ids=(),
    ),
)


def _bundle(bundle_id: str, handlers, lineage: ExtensionLineage) -> HandlerBundleManifest:
    payload = {
        "bundle_id": bundle_id, "bundle_version": "1.0.0",
        "handlers": tuple(handlers), "lineage": lineage,
    }
    return HandlerBundleManifest(**payload, bundle_hash=hashed_payload(payload))


def build_profile_bundle(lineage): return _bundle("p3.s38.company.profile", PROFILE_BINDINGS, lineage)
def build_statement_bundle(lineage): return _bundle("p3.s38.company.statements", STATEMENT_BINDINGS, lineage)
def build_analysis_bundle(lineage): return _bundle("p3.s38.company.analysis", ANALYSIS_BINDINGS, lineage)
def build_guidance_valuation_bundle(lineage):
    return _bundle("p3.s38.company.guidance.peers.valuation", GUIDANCE_PEER_VALUATION_BINDINGS, lineage)


@dataclass(frozen=True, slots=True)
class CompanyHandlerFactory:
    query_port: PitResearchQueryPort

    def build(self):
        return {
            "get_profile": GetProfileHandler(self.query_port),
            "get_financial_statements": GetFinancialStatementsHandler(self.query_port),
            "get_fundamental_snapshot": GetFundamentalSnapshotHandler(self.query_port),
            "get_guidance": GetGuidanceHandler(self.query_port),
            "get_capital_allocation": GetCapitalAllocationHandler(self.query_port),
            "get_peers": GetPeersHandler(self.query_port),
            "calculate_valuation": CalculateValuationHandler(self.query_port),
        }
