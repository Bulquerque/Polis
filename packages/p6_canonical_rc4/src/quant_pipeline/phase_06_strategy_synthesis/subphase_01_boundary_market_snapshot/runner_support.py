"""Typed module implementations for P6.S1."""

from __future__ import annotations

from typing import Any

from ..boundaries.p2 import parse_contracts, parse_quotes, parse_underlyings
from ..boundaries.p5 import parse_p5_handoff
from ..domain.models import StaticArbitrageViolation
from ..foundation.artifacts import ArtifactStatus, build_artifact
from ..foundation.context import PhaseContext
from ..foundation.contracts import external_artifact_id
from ..foundation.results import ModuleResult
from .services import build_snapshot, classify_quote, static_arbitrage_diagnostics


def _artifact(records, artifact_type, module_id, context, inputs=(), status=None, metadata=None):
    return build_artifact(
        artifact_type=artifact_type,
        producer_module_id=module_id,
        run_id=context.run_id,
        cycle_id=context.cycle_id,
        decision_time=context.decision_time,
        created_at=context.created_at,
        available_at=context.available_at,
        records=records,
        input_artifact_ids=inputs,
        status=status,
        metadata=metadata,
    )


def validate_beliefs(
    inputs: dict[str, Any],
    context: PhaseContext,
    configuration: Any | None = None,
) -> ModuleResult:
    module_id = "P6.S1.M01"
    maximum = 101 if configuration is None else configuration.p5.max_distribution_scenarios
    parsed = parse_p5_handoff(
        inputs,
        context.decision_time,
        module_id,
        max_distribution_scenarios=maximum,
        expected_run_id=context.run_id,
        expected_cycle_id=context.cycle_id,
    )
    metadata = {
        "p5_manifest_id": parsed.report.manifest_id,
        "p5_manifest_sha256": parsed.report.manifest_sha256,
        "p5_contract_version": parsed.report.p5_contract_version,
        "p5_full_manifest_consumed": parsed.report.full_manifest_consumed,
    }
    p5_input_ids = (
        parsed.report.manifest_id,
        *(receipt.artifact_id for receipt in parsed.report.receipts),
    )
    artifact = _artifact(
        parsed.beliefs,
        "validated_market_belief_state",
        module_id,
        context,
        inputs=p5_input_ids,
        metadata=metadata,
    )
    report = _artifact(
        (parsed.report,),
        "p5_handoff_compatibility_report",
        module_id,
        context,
        inputs=p5_input_ids,
        metadata=metadata,
    )
    return ModuleResult(module_id=module_id, outputs={
        "validated_market_belief_state": artifact,
        "p5_handoff_compatibility_report": report,
    })


def validate_options(inputs: dict[str, Any], context: PhaseContext) -> ModuleResult:
    module_id = "P6.S1.M02"
    contracts = parse_contracts(inputs, module_id)
    quotes = tuple(classify_quote(item) for item in parse_quotes(inputs, context.decision_time, module_id))
    contract_artifact = _artifact(contracts, "validated_option_contract_panel", module_id, context)
    quote_artifact = _artifact(quotes, "validated_option_quote_panel", module_id, context)
    return ModuleResult(module_id=module_id, outputs={
        "validated_option_contract_panel": contract_artifact,
        "validated_option_quote_panel": quote_artifact,
    })


def validate_underlyings(inputs: dict[str, Any], context: PhaseContext) -> ModuleResult:
    module_id = "P6.S1.M03"
    records = parse_underlyings(inputs, context.decision_time, module_id)
    artifact = _artifact(records, "validated_underlying_panel", module_id, context)
    return ModuleResult(module_id=module_id, outputs={"validated_underlying_panel": artifact})


def diagnose_arbitrage(inputs: dict[str, Any], context: PhaseContext) -> ModuleResult:
    module_id = "P6.S1.M04"
    contracts = tuple(inputs["validated_option_contract_panel"].records)
    quotes = tuple(inputs["validated_option_quote_panel"].records)
    underlyings = tuple(inputs["validated_underlying_panel"].records)
    violations = static_arbitrage_diagnostics(contracts, quotes, underlyings)
    blocking = {contract_id for item in violations if item.severity == "BLOCKING" for contract_id in item.contract_ids}
    filtered_quotes = tuple(item for item in quotes if item.contract_id not in blocking)
    report = _artifact(
        violations,
        "static_arbitrage_report",
        module_id,
        context,
        inputs=(
            inputs["validated_option_contract_panel"].artifact_id,
            inputs["validated_option_quote_panel"].artifact_id,
            inputs["validated_underlying_panel"].artifact_id,
        ),
        status=ArtifactStatus.COMPLETE if violations else ArtifactStatus.EMPTY_VALID,
    )
    filtered = _artifact(
        filtered_quotes,
        "arbitrage_validated_option_quote_panel",
        module_id,
        context,
        inputs=(inputs["validated_option_quote_panel"].artifact_id, report.artifact_id),
        status=ArtifactStatus.COMPLETE if filtered_quotes else ArtifactStatus.EMPTY_VALID,
        metadata={"repair_applied": False},
    )
    return ModuleResult(module_id=module_id, outputs={
        "static_arbitrage_report": report,
        "arbitrage_validated_option_quote_panel": filtered,
    })


def build_market_snapshot(inputs: dict[str, Any], context: PhaseContext) -> ModuleResult:
    module_id = "P6.S1.M05"
    belief = inputs["validated_market_belief_state"]
    contracts = inputs["validated_option_contract_panel"]
    quotes = inputs["arbitrage_validated_option_quote_panel"]
    underlyings = inputs["validated_underlying_panel"]
    report = inputs["static_arbitrage_report"]
    compatibility = inputs.get("p5_handoff_compatibility_report")
    compatibility_record = None if compatibility is None or not compatibility.records else compatibility.records[0]
    receipts = () if compatibility_record is None else compatibility_record.receipts
    record = build_snapshot(
        decision_time=context.decision_time,
        belief_artifact_id=belief.artifact_id,
        contract_artifact_id=contracts.artifact_id,
        quote_artifact_id=quotes.artifact_id,
        underlying_artifact_id=underlyings.artifact_id,
        rejection_report_artifact_id=report.artifact_id,
        p5_compatibility_report_artifact_id=None if compatibility is None else compatibility.artifact_id,
        p5_manifest_id=None if compatibility_record is None else compatibility_record.manifest_id,
        p5_manifest_sha256=None if compatibility_record is None else compatibility_record.manifest_sha256,
        p5_source_artifact_ids=tuple(item.artifact_id for item in receipts),
        p5_source_hashes=tuple(item.artifact_sha256 for item in receipts),
        beliefs=belief.records,
        contracts=contracts.records,
        quotes=quotes.records,
        underlyings=underlyings.records,
    )
    artifact = _artifact(
        (record,),
        "strategy_market_snapshot",
        module_id,
        context,
        inputs=(
            belief.artifact_id,
            contracts.artifact_id,
            quotes.artifact_id,
            underlyings.artifact_id,
            report.artifact_id,
            *(() if compatibility is None else (compatibility.artifact_id,)),
        ),
    )
    return ModuleResult(module_id=module_id, outputs={"strategy_market_snapshot": artifact})
