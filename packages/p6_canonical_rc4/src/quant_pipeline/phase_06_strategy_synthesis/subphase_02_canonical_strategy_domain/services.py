"""Contract existence, declarative registries, and stable identity policy."""

from __future__ import annotations

from ..domain.enums import ExerciseStyle, ObjectiveFamily, SettlementType, TemplateId
from ..domain.models import ExecutableQuote, OptionContractReference, RejectionRecord
from ..foundation.configuration import Phase6RunConfiguration
from ..foundation.hashing import stable_id
from .registry_models import (
    ConstraintDefinition,
    ObjectiveDefinition,
    StrategyIdentityPolicy,
    TemplateDefinition,
)


def contract_existence_gate(
    contracts: tuple[OptionContractReference, ...],
    quotes: tuple[ExecutableQuote, ...],
    configuration: Phase6RunConfiguration,
) -> tuple[tuple[OptionContractReference, ...], tuple[ExecutableQuote, ...], tuple[RejectionRecord, ...]]:
    quote_by_id = {item.contract_id: item for item in quotes}
    eligible_contracts: list[OptionContractReference] = []
    eligible_quotes: list[ExecutableQuote] = []
    rejections: list[RejectionRecord] = []
    for contract in contracts:
        reason = _contract_rejection_reason(contract, quote_by_id.get(contract.contract_id), configuration)
        if reason is not None:
            rejections.append(RejectionRecord(
                rejection_id=stable_id("rejection", contract.contract_id, reason),
                stage="P6.S2.M01",
                reason_code=reason,
                details={"contract_id": contract.contract_id},
            ))
            continue
        eligible_contracts.append(contract)
        eligible_quotes.append(quote_by_id[contract.contract_id])
    return tuple(eligible_contracts), tuple(eligible_quotes), tuple(rejections)


def _contract_rejection_reason(
    contract: OptionContractReference,
    quote: ExecutableQuote | None,
    configuration: Phase6RunConfiguration,
) -> str | None:
    decision = configuration.decision_time
    if contract.first_trade_date > decision:
        return "P6_CONTRACT_NOT_LISTED"
    if contract.expiration <= decision or (
        contract.last_trade_date is not None and contract.last_trade_date < decision
    ):
        return "P6_CONTRACT_EXPIRED"
    if contract.contract_status != "ACTIVE":
        return "P6_CONTRACT_INVALID_AT_DECISION"
    if contract.exercise_style is ExerciseStyle.AMERICAN:
        return (
            "P6_AMERICAN_OPTION_VALUATION_UNAVAILABLE"
            if configuration.strategy.allow_american_options
            else "P6_EXERCISE_STYLE_UNSUPPORTED"
        )
    if contract.settlement_type not in (SettlementType.CASH, SettlementType.PHYSICAL):
        return "P6_SETTLEMENT_UNSUPPORTED"
    if quote is None or quote.ask is None or quote.bid is None:
        return "P6_QUOTE_UNAVAILABLE"
    return None


def template_registry() -> tuple[TemplateDefinition, ...]:
    specs = (
        (TemplateId.LONG_UNDERLYING, ObjectiveFamily.DIRECTIONAL_UP, 1, 1, True),
        (TemplateId.SHORT_UNDERLYING, ObjectiveFamily.DIRECTIONAL_DOWN, 1, 1, False),
        (TemplateId.LONG_CALL, ObjectiveFamily.DIRECTIONAL_UP, 1, 1, True),
        (TemplateId.LONG_PUT, ObjectiveFamily.DIRECTIONAL_DOWN, 1, 1, True),
        (TemplateId.BULL_CALL_DEBIT, ObjectiveFamily.DIRECTIONAL_UP, 2, 2, True),
        (TemplateId.BEAR_PUT_DEBIT, ObjectiveFamily.DIRECTIONAL_DOWN, 2, 2, True),
        (TemplateId.BULL_PUT_CREDIT, ObjectiveFamily.INCOME_DEFINED_RISK, 2, 2, True),
        (TemplateId.BEAR_CALL_CREDIT, ObjectiveFamily.INCOME_DEFINED_RISK, 2, 2, True),
        (TemplateId.LONG_STRADDLE, ObjectiveFamily.LONG_VOLATILITY, 2, 2, True),
        (TemplateId.LONG_STRANGLE, ObjectiveFamily.LONG_VOLATILITY, 2, 2, True),
        (TemplateId.LONG_CALL_BUTTERFLY, ObjectiveFamily.POSITIVE_CONVEXITY, 3, 3, True),
        (TemplateId.LONG_CALL_CONDOR, ObjectiveFamily.RANGE, 4, 4, True),
        (TemplateId.IRON_BUTTERFLY, ObjectiveFamily.SHORT_VOLATILITY_DEFINED_RISK, 4, 4, True),
        (TemplateId.IRON_CONDOR, ObjectiveFamily.SHORT_VOLATILITY_DEFINED_RISK, 4, 4, True),
        (TemplateId.COLLAR, ObjectiveFamily.PORTFOLIO_HEDGE, 3, 3, True),
        (TemplateId.RISK_REVERSAL_DEFINED_RISK, ObjectiveFamily.SKEW_RELATIVE_VALUE, 2, 2, True),
        (TemplateId.PROTECTED_RATIO_CALL, ObjectiveFamily.HYBRID, 4, 4, True),
    )
    return tuple(TemplateDefinition(
        template_id=template,
        objective_family=objective,
        minimum_legs=minimum,
        maximum_legs=maximum,
        defined_risk_expected=defined,
        description=template.value.replace("_", " ").title(),
    ) for template, objective, minimum, maximum, defined in specs)


def objective_registry() -> tuple[ObjectiveDefinition, ...]:
    return tuple(ObjectiveDefinition(
        objective_family=family,
        description=family.value.replace("_", " ").title(),
    ) for family in ObjectiveFamily)


def constraint_registry(configuration: Phase6RunConfiguration) -> tuple[ConstraintDefinition, ...]:
    return (ConstraintDefinition(
        policy_version=configuration.strategy.policy_version,
        max_legs=configuration.budgets.max_legs,
        max_expirations=configuration.budgets.max_expirations,
        max_quantity=configuration.budgets.max_quantity,
        require_defined_risk=configuration.risk.require_defined_risk,
        allowed_exercise_styles=(
            ("EUROPEAN",)
            if not configuration.strategy.allow_american_options
            else ("EUROPEAN", "AMERICAN")
        ),
        allowed_settlement_types=("CASH", "PHYSICAL"),
    ),)


def identity_policy(configuration: Phase6RunConfiguration) -> tuple[StrategyIdentityPolicy, ...]:
    return (StrategyIdentityPolicy(
        policy_version=configuration.strategy.policy_version,
        content_fields=(
            "underlying_id",
            "decision_time",
            "canonical_legs",
            "objective_family",
            "generation_policy_version",
        ),
    ),)
