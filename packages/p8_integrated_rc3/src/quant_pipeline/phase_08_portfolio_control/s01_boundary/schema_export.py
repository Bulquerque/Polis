"""Export strict Draft 2020-12 JSON schemas from the canonical Pydantic models."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import TypeAdapter

from quant_pipeline.phase_08_contracts.p5 import P5BeliefEvidenceBundleV1
from quant_pipeline.phase_08_contracts.p6 import P6CandidateEconomicPackageV1
from quant_pipeline.phase_08_contracts.p7 import P7RankingHandoffV1
from quant_pipeline.phase_08_contracts.p9 import (
    P0PolicyAuthorizationV1,
    P9FeedbackRecommendationV1,
    PromotedFeedback,
)
from quant_pipeline.phase_08_contracts.s1 import (
    CandidateTerminalStateLedger,
    P8DecisionSnapshot,
    Phase7ConsumptionReceipt,
    PromotedPortfolioFeedbackContext,
    ResolvedCandidateEvidenceIndex,
    ValidatedP7HandoffBundle,
)
from quant_pipeline.phase_08_contracts.state import (
    AccountSnapshot,
    CurrentPortfolioAndAccountState,
    PortfolioStateProjection,
)


_SCHEMA_MODELS = {
    "P7_TO_P8_RANKING_HANDOFF_V1.schema.json": P7RankingHandoffV1,
    "P6_CANDIDATE_ECONOMIC_PACKAGE_V1.schema.json": P6CandidateEconomicPackageV1,
    "P5_BELIEF_EVIDENCE_REFERENCE_BUNDLE_V1.schema.json": P5BeliefEvidenceBundleV1,
    "P9_FEEDBACK_RECOMMENDATION_V1.schema.json": P9FeedbackRecommendationV1,
    "P0_POLICY_AUTHORIZATION_V1.schema.json": P0PolicyAuthorizationV1,
    "VALIDATED_P7_HANDOFF_BUNDLE_V1.schema.json": ValidatedP7HandoffBundle,
    "CANDIDATE_TERMINAL_STATE_LEDGER_V1.schema.json": CandidateTerminalStateLedger,
    "RESOLVED_CANDIDATE_EVIDENCE_INDEX_V1.schema.json": ResolvedCandidateEvidenceIndex,
    "PROMOTED_PORTFOLIO_FEEDBACK_CONTEXT_V1.schema.json": PromotedPortfolioFeedbackContext,
    "PORTFOLIO_STATE_PROJECTION_V1.schema.json": PortfolioStateProjection,
    "ACCOUNT_SNAPSHOT_V1.schema.json": AccountSnapshot,
    "CURRENT_PORTFOLIO_ACCOUNT_STATE_V1.schema.json": CurrentPortfolioAndAccountState,
    "P8_DECISION_SNAPSHOT_V1.schema.json": P8DecisionSnapshot,
    "PHASE7_CONSUMPTION_RECEIPT_V1.schema.json": Phase7ConsumptionReceipt,
}


def _normalize_schema(schema: dict[str, object], *, schema_id: str) -> dict[str, object]:
    normalized = dict(schema)
    normalized["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    normalized["$id"] = schema_id
    return normalized


def export_schemas(target: Path) -> tuple[Path, ...]:
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, model in _SCHEMA_MODELS.items():
        schema = model.model_json_schema(mode="validation")
        path = target / filename
        path.write_text(
            json.dumps(_normalize_schema(schema, schema_id=filename), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    feedback_schema = TypeAdapter(PromotedFeedback).json_schema(mode="validation")
    feedback_path = target / "P9_TO_P8_PROMOTED_FEEDBACK_V1.schema.json"
    feedback_path.write_text(
        json.dumps(
            _normalize_schema(feedback_schema, schema_id="P9_TO_P8_PROMOTED_FEEDBACK_V1.schema.json"),
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    written.append(feedback_path)
    return tuple(written)
