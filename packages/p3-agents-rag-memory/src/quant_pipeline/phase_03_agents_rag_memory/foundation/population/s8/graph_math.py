"""Pure formulas for homophily, trust and deterministic edge selection."""
from __future__ import annotations

import math

from .models import SocialGraphConfig, SocialNode, TrustDomainFormula


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return min(high, max(low, value))


def sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def tag_cosine(left: SocialNode, right: SocialNode) -> float:
    left_map = {item.tag_id: item.effective_value for item in left.tags}
    right_map = {item.tag_id: item.effective_value for item in right.tags}
    keys = sorted(set(left_map) | set(right_map))
    dot = math.fsum(left_map.get(key, 0.0) * right_map.get(key, 0.0) for key in keys)
    left_norm = math.sqrt(math.fsum(left_map.get(key, 0.0) ** 2 for key in keys))
    right_norm = math.sqrt(math.fsum(right_map.get(key, 0.0) ** 2 for key in keys))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return clamp(dot / (left_norm * right_norm))


def role_similarity(left: SocialNode, right: SocialNode) -> float:
    if left.economic_role == right.economic_role:
        return 1.0
    if left.role_family == right.role_family:
        return 0.6
    return 0.0


def same_institution(left: SocialNode, right: SocialNode) -> float:
    return float(
        left.institution_type is not None
        and right.institution_type is not None
        and left.institution_type == right.institution_type
    )


def same_geography(left: SocialNode, right: SocialNode) -> float:
    return float(left.geography.casefold() == right.geography.casefold())


def pair_probability(left: SocialNode, right: SocialNode, config: SocialGraphConfig) -> float:
    weights = config.probability_weights
    score = (
        weights.intercept
        + same_institution(left, right) * weights.same_institution
        + role_similarity(left, right) * weights.role_similarity
        + tag_cosine(left, right) * weights.tag_cosine
        + same_geography(left, right) * weights.same_geography
    )
    return clamp(sigmoid(score))


def relationship_type(left: SocialNode, right: SocialNode) -> str:
    if same_institution(left, right):
        return "institutional_peer"
    if left.economic_role == right.economic_role:
        return "role_peer"
    if left.role_family != right.role_family:
        return "cross_role_bridge"
    if same_geography(left, right):
        return "geographic_peer"
    return "professional_peer"


def _formula_value(source: SocialNode, target: SocialNode, formula: TrustDomainFormula) -> float:
    capabilities = target.capabilities
    resources = target.resources
    raw = (
        formula.base
        + capabilities.research * formula.target_research
        + capabilities.quantitative * formula.target_quantitative
        + capabilities.verbal * formula.target_verbal
        + capabilities.coding * formula.target_coding
        + capabilities.tool_use * formula.target_tool_use
        + resources.information_access * formula.target_information_access
        + tag_cosine(source, target) * formula.pair_tag_cosine
        + same_institution(source, target) * formula.same_institution
        + role_similarity(source, target) * formula.role_similarity
    )
    coefficient_sum = max(1.0, sum(formula.model_dump().values()))
    return clamp(raw / coefficient_sum)


def domain_trust(source: SocialNode, target: SocialNode, config: SocialGraphConfig) -> dict[str, float]:
    return {
        domain: _formula_value(source, target, config.trust_domain_formulas[domain])
        for domain in sorted(config.trust_domains)
    }


def global_trust(source: SocialNode, target: SocialNode, values: dict[str, float], config: SocialGraphConfig) -> float:
    mean_domain = math.fsum(values.values()) / len(values)
    structural = (
        0.40 * tag_cosine(source, target)
        + 0.25 * role_similarity(source, target)
        + 0.20 * same_institution(source, target)
        + 0.15 * same_geography(source, target)
    )
    value = 0.65 * mean_domain + 0.35 * structural
    return clamp(value, config.global_trust_floor, config.global_trust_ceiling)


def influence(source: SocialNode, target: SocialNode) -> float:
    del source
    return clamp(
        0.15
        + 0.30 * target.capabilities.verbal
        + 0.25 * target.resources.information_access
        + 0.15 * target.capabilities.research
        + 0.15 * target.capabilities.quantitative
    )


def interaction_frequency(left: SocialNode, right: SocialNode) -> float:
    return clamp(
        0.10
        + 0.20 * same_institution(left, right)
        + 0.15 * same_geography(left, right)
        + 0.20 * role_similarity(left, right)
        + 0.35 * tag_cosine(left, right)
    )
