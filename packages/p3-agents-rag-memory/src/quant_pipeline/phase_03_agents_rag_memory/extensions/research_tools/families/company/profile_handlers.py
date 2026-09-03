"""Profile, guidance, and peer handlers."""
from __future__ import annotations

from dataclasses import dataclass

from .data_access import query_company_records, view_declared
from .models import (
    CompanyCallContext, GetGuidanceRequest, GetPeersRequest, GetProfileRequest, OutcomeStatus,
)
from .outcomes import build_company_result
from .ports import PitResearchQueryPort


@dataclass(frozen=True, slots=True)
class GetProfileHandler:
    query_port: PitResearchQueryPort

    async def execute(self, request: GetProfileRequest, context: CompanyCallContext):
        visible, rejected = await query_company_records(
            self.query_port, view_id=request.view_id, entity_id=request.entity_id,
            decision_time=context.decision_time,
        )
        records = tuple(sorted(visible, key=lambda item: str(item.get("effective_from", item.get("available_at")))))
        latest = records[-1:] if records else ()
        return build_company_result(
            operation_id="get_profile", requested_mode=request.research_mode, executed_mode=request.research_mode,
            method_id="company.profile.pit.v1", metrics={"versions_visible": len(records)}, records=latest,
            records_requested=1, records_rejected_future=rejected,
            missing_requirements=(() if records else ("company_profile",)),
            outcome_status=(None if records else OutcomeStatus.BLOCKED_UPSTREAM),
            reason_codes=(() if records else ("P3RT-UPSTREAM-COMPANY-PROFILE-MISSING",)),
        )


@dataclass(frozen=True, slots=True)
class GetGuidanceHandler:
    query_port: PitResearchQueryPort

    async def execute(self, request: GetGuidanceRequest, context: CompanyCallContext):
        visible, rejected = await query_company_records(
            self.query_port, view_id=request.view_id, entity_id=request.entity_id,
            decision_time=context.decision_time, extra_filters={"metric_ids": list(request.metric_ids)},
        )
        records = tuple(item for item in visible if request.include_withdrawn or not item.get("withdrawn_at"))
        empty_valid = not records and view_declared(self.query_port, request.view_id)
        return build_company_result(
            operation_id="get_guidance", requested_mode=request.research_mode, executed_mode=request.research_mode,
            method_id="company.guidance.pit.v1", metrics={"guidance_records": len(records)}, records=records,
            records_requested=max(len(request.metric_ids), 1), records_rejected_future=rejected,
            missing_requirements=(() if records or empty_valid else ("company_guidance",)),
            outcome_status=(None if records else (OutcomeStatus.EMPTY_VALID if empty_valid else OutcomeStatus.BLOCKED_UPSTREAM)),
            reason_codes=(
                ("P3RT-COMPANY-GUIDANCE-EMPTY-VALID",) if empty_valid
                else (() if records else ("P3RT-UPSTREAM-COMPANY-GUIDANCE-MISSING",))
            ),
        )


@dataclass(frozen=True, slots=True)
class GetPeersHandler:
    query_port: PitResearchQueryPort

    async def execute(self, request: GetPeersRequest, context: CompanyCallContext):
        visible, rejected = await query_company_records(
            self.query_port, view_id=request.view_id, entity_id=request.entity_id,
            decision_time=context.decision_time,
            extra_filters={"authority_classes": list(request.authority_classes)},
        )
        allowed = set(request.authority_classes)
        records = tuple(item for item in visible if str(item.get("authority_class", "DOCUMENTED")) in allowed)
        records = records[: request.maximum_peers]
        empty_valid = not records and view_declared(self.query_port, request.view_id)
        return build_company_result(
            operation_id="get_peers", requested_mode=request.research_mode, executed_mode=request.research_mode,
            method_id="company.peers.temporal.v1", metrics={"peer_count": len(records)}, records=records,
            records_requested=request.maximum_peers, records_rejected_future=rejected,
            missing_requirements=(() if records or empty_valid else ("company_peers",)),
            outcome_status=(None if records else (OutcomeStatus.EMPTY_VALID if empty_valid else OutcomeStatus.BLOCKED_UPSTREAM)),
            reason_codes=(
                ("P3RT-COMPANY-PEERS-EMPTY-VALID",) if empty_valid
                else (() if records else ("P3RT-UPSTREAM-COMPANY-PEERS-MISSING",))
            ),
        )
