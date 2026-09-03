
"""P8.S2.M01 — normalize P6 candidates into unit economic intents."""

from __future__ import annotations

from decimal import Decimal

from quant_pipeline.phase_08_contracts.canonical import canonical_sha256
from quant_pipeline.phase_08_contracts.enums import EvidenceResolutionStatus, PositionSide

from ..context import S2ExecutionContext
from ..contracts.intent import (
    NormalizedCandidateIntent,
    NormalizedCandidateIntentPanel,
    NormalizedLeg,
    NormalizedUnitEconomics,
)
from ..contracts.results import M01Result
from ..errors import CandidateNormalizationError
from ..module_support import build_receipt, seal

MODULE_ID = "P8.S2.M01"


def run_module(bundle, *, context: S2ExecutionContext) -> M01Result:
    handoff = bundle.validated_handoff.handoff
    ranked_by_id = {row.candidate_id: row for row in handoff.ranked}
    evidence_by_id = {row.candidate_id: row for row in bundle.resolved_evidence.candidates}
    rows: list[NormalizedCandidateIntent] = []
    for candidate_id in sorted(bundle.snapshot.actionable_ranked_candidate_ids):
        ranked = ranked_by_id.get(candidate_id)
        evidence = evidence_by_id.get(candidate_id)
        if ranked is None or evidence is None:
            raise CandidateNormalizationError(f"actionable candidate missing ranked/evidence record: {candidate_id}")
        if evidence.status not in {EvidenceResolutionStatus.RESOLVED, EvidenceResolutionStatus.ADAPTED_LOSSLESS}:
            raise CandidateNormalizationError(f"candidate evidence is not resolved: {candidate_id}")
        if evidence.p6_package is None or evidence.p5_belief_bundle is None:
            raise CandidateNormalizationError(f"candidate lacks P6/P5 payload: {candidate_id}")
        package = evidence.p6_package
        if package.candidate_id != candidate_id or package.canonical_candidate_id != ranked.canonical_candidate_id:
            raise CandidateNormalizationError(f"P6/P7 candidate identity mismatch: {candidate_id}")
        legs: list[NormalizedLeg] = []
        for index, leg in enumerate(package.legs, start=1):
            if leg.unit_quantity <= 0:
                raise CandidateNormalizationError(
                    f"unit_quantity must be a positive magnitude because side carries sign: {candidate_id}"
                )
            signed = leg.unit_quantity if leg.side is PositionSide.LONG else -leg.unit_quantity
            leg_id = f"{candidate_id}:leg:{index:03d}"
            legs.append(NormalizedLeg(
                leg_id=leg_id,
                instrument_id=leg.instrument_id,
                instrument_type=leg.instrument_type,
                side=leg.side,
                contract_quantity_per_candidate_unit=leg.unit_quantity,
                signed_contract_quantity_per_candidate_unit=signed,
                contract_multiplier=leg.contract_multiplier,
                strike=leg.strike,
                expiration=leg.expiration.isoformat().replace("+00:00", "Z") if leg.expiration else None,
                exercise_style=leg.exercise_style,
                settlement_type=leg.settlement_type,
                instrument_master_hash=leg.instrument_master_ref.content_sha256,
            ))
        economics = package.unit_economics
        row = NormalizedCandidateIntent(
            candidate_id=candidate_id,
            canonical_candidate_id=package.canonical_candidate_id,
            comparison_group_id=ranked.comparison_group_id,
            candidate_family=package.candidate_family,
            objective_family=package.objective_family,
            unit_definition=package.unit_definition,
            currency=package.currency,
            lot_size=package.lot_size,
            quantity_increment=package.quantity_increment,
            legs=tuple(sorted(legs, key=lambda item: item.leg_id)),
            unit_economics=NormalizedUnitEconomics(
                entry_cost_status=economics.entry_cost_status,
                payoff_status=economics.payoff_status,
                maximum_loss_status=economics.maximum_loss_status,
                liquidity_status=economics.liquidity_status,
                lifecycle_status=economics.lifecycle_status,
                unit_entry_cost=economics.unit_entry_cost,
                unit_maximum_loss=economics.unit_maximum_loss,
                margin_per_unit=economics.margin_per_unit,
                liquidity_capacity_units=economics.liquidity_capacity_units,
            ),
            p6_package_hash=canonical_sha256(package),
            p5_belief_bundle_hash=canonical_sha256(evidence.p5_belief_bundle),
            p5_evidence_signature_hash=canonical_sha256((
                evidence.p5_belief_bundle.target_id,
                evidence.p5_belief_bundle.underlying_or_factor_id,
                evidence.p5_belief_bundle.forecast_horizon,
                evidence.p5_belief_bundle.resolver_id,
                evidence.p5_belief_bundle.model_artifact_id,
                evidence.p5_belief_bundle.probability_measure,
                evidence.p5_belief_bundle.forecast_distribution_ref,
                evidence.p5_belief_bundle.quantile_panel_ref,
                evidence.p5_belief_bundle.scenario_set_ref,
                evidence.p5_belief_bundle.path_scenario_ref,
                evidence.p5_belief_bundle.covariance_dependence_ref,
                evidence.p5_belief_bundle.regime_state_ref,
                evidence.p5_belief_bundle.ood_state_ref,
                evidence.p5_belief_bundle.disagreement_ref,
                evidence.p5_belief_bundle.calibration_ref,
                evidence.p5_belief_bundle.ambiguity_evidence_ref,
                evidence.p5_belief_bundle.ensemble_weights_ref,
                tuple(sorted(ref.content_sha256 for ref in evidence.p5_belief_bundle.view_refs)),
            )),
            source_score_semantics=ranked.score_semantics.value,
        )
        rows.append(row)
    provisional = NormalizedCandidateIntentPanel(
        contract_version="P8_NORMALIZED_CANDIDATE_INTENT_PANEL_V1",
        schema_version="1.0.0",
        snapshot_id=bundle.snapshot.snapshot_id,
        candidates=tuple(rows),
        content_sha256="0" * 64,
    )
    panel = seal(provisional)
    receipt = build_receipt(
        module_id=MODULE_ID,
        inputs=(bundle.snapshot, bundle.resolved_evidence, bundle.validated_handoff),
        output=panel,
        computed_at=context.computed_at,
    )
    return M01Result(normalized_intents=panel, receipt=receipt)

run_m01 = run_module
