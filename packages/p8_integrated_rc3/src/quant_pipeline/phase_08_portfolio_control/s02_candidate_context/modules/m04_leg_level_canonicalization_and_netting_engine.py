
"""P8.S2.M04 — publish a symbolic virtual-to-physical transform, never final net orders."""

from __future__ import annotations

from collections import defaultdict

from ..context import S2ExecutionContext
from ..contracts.enums import VirtualIntentState
from ..contracts.netting import (
    CandidateInstrumentCoefficient,
    CurrentPhysicalPositionBaseline,
    NettingTransform,
    NettingTransformProof,
    VirtualCandidateIntentRecord,
)
from ..contracts.results import M04Result
from ..errors import NettingIntegrityError
from ..module_support import build_receipt, seal

MODULE_ID = "P8.S2.M04"


def run_module(bundle, m01, *, context: S2ExecutionContext) -> M04Result:
    coefficients_by_key: dict[tuple[str, str], CandidateInstrumentCoefficient] = {}
    instrument_conventions: dict[str, tuple[object, object]] = {}
    virtual_rows: list[VirtualCandidateIntentRecord] = []
    for candidate in m01.normalized_intents.candidates:
        virtual_rows.append(VirtualCandidateIntentRecord(
            candidate_id=candidate.candidate_id,
            canonical_candidate_id=candidate.canonical_candidate_id,
            unit_definition=candidate.unit_definition,
            state=VirtualIntentState.ACTIVE_FOR_SIZING,
        ))
        summed: defaultdict[str, object] = defaultdict(lambda: 0)
        leg_meta: dict[str, tuple[object, object]] = {}
        for leg in candidate.legs:
            convention = (leg.contract_multiplier, candidate.currency)
            prior = instrument_conventions.get(leg.instrument_id)
            if prior is not None and prior != convention:
                raise NettingIntegrityError(f"instrument convention conflict: {leg.instrument_id}")
            instrument_conventions[leg.instrument_id] = convention
            if leg.instrument_id in leg_meta and leg_meta[leg.instrument_id] != convention:
                raise NettingIntegrityError(f"candidate repeats instrument with conflicting convention: {leg.instrument_id}")
            leg_meta[leg.instrument_id] = convention
            summed[leg.instrument_id] += leg.signed_contract_quantity_per_candidate_unit
        nonzero_instruments = [instrument_id for instrument_id in sorted(summed) if summed[instrument_id] != 0]
        if not nonzero_instruments:
            raise NettingIntegrityError(f"candidate has zero net physical exposure: {candidate.candidate_id}")
        for instrument_id in nonzero_instruments:
            value = summed[instrument_id]
            multiplier, currency = leg_meta[instrument_id]
            row = CandidateInstrumentCoefficient(
                candidate_id=candidate.candidate_id,
                instrument_id=instrument_id,
                signed_contracts_per_candidate_unit=value,
                contract_multiplier=multiplier,
                currency=currency,
            )
            coefficients_by_key[(candidate.candidate_id, instrument_id)] = row
    current_rows: list[CurrentPhysicalPositionBaseline] = []
    for position in sorted(bundle.current_state.portfolio_state.positions, key=lambda item: item.instrument_id):
        prior = instrument_conventions.get(position.instrument_id)
        convention = (position.contract_multiplier, position.currency)
        if prior is not None and prior != convention:
            raise NettingIntegrityError(f"current position convention conflicts with candidate: {position.instrument_id}")
        current_rows.append(CurrentPhysicalPositionBaseline(
            instrument_id=position.instrument_id,
            current_contract_quantity=position.quantity,
            contract_multiplier=position.contract_multiplier,
            currency=position.currency,
            virtual_attribution_status="NOT_REQUIRED_ZERO_POSITION" if position.quantity == 0 else "UNAVAILABLE_IN_S1_STATE",
        ))
    mapped = {row.candidate_id for row in coefficients_by_key.values()}
    active = {row.candidate_id for row in virtual_rows}
    provisional = NettingTransform(
        contract_version="P8_NETTING_TRANSFORM_V1",
        schema_version="1.0.0",
        snapshot_id=bundle.snapshot.snapshot_id,
        virtual_intents=tuple(sorted(virtual_rows, key=lambda item: item.candidate_id)),
        coefficients=tuple(coefficients_by_key[key] for key in sorted(coefficients_by_key)),
        current_positions=tuple(current_rows),
        proof=NettingTransformProof(
            candidate_count=len(active),
            instrument_count=len({row.instrument_id for row in coefficients_by_key.values()}),
            coefficient_count=len(coefficients_by_key),
            all_active_candidates_mapped=active == mapped,
            equation_semantics="target_physical_quantity = current_physical_quantity + sum(coefficient * virtual_candidate_quantity)",
        ),
        content_sha256="0" * 64,
    )
    transform = seal(provisional)
    receipt = build_receipt(
        module_id=MODULE_ID,
        inputs=(m01.normalized_intents, bundle.current_state),
        output=transform,
        computed_at=context.computed_at,
    )
    return M04Result(netting_transform=transform, receipt=receipt)

run_m04 = run_module
