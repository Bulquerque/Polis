"""Declarative feature and structural filters for P4 consumer views."""
from __future__ import annotations

from typing import Any

from ..errors import DataQualityError, ReasonCode
from .models import canonical_sha256

_STRUCTURAL_FILTERS = {
    "normalized_values", "missingness_mask", "source_modalities",
    "sequence_order", "age_of_information",
}


def view_filter_report(
    view_id: str, filters: tuple[str, ...], records: list[dict[str, Any]],
) -> dict[str, Any]:
    included = sorted({name for row in records for name in row["included_feature_ids"]})
    excluded = sorted({name for row in records for name in row["excluded_feature_ids"]})
    matched = sorted({rule for row in records for rule in row["matched_filters"]})
    mandatory, optional = split_rules(filters)
    unmatched_mandatory = sorted(set(mandatory) - set(matched))
    unmatched_optional = sorted(set(optional) - set(matched))
    if unmatched_mandatory:
        raise DataQualityError(
            f"P4 view {view_id} has unmatched mandatory filters: {unmatched_mandatory}",
            reason_code=ReasonCode.VIEW_FILTER_UNMATCHED,
        )
    payload = {
        "view_id": view_id,
        "included_feature_ids": included,
        "excluded_feature_ids": excluded,
        "filter_match_count": len(matched),
        "unmatched_filters": unmatched_optional,
        "matched_filters": matched,
    }
    return {**payload, "materialized_view_hash": canonical_sha256({**payload, "records": records})}


def apply_filters(
    features: dict[str, Any],
    metadata: dict[str, dict[str, Any]],
    filters: tuple[str, ...],
    row: dict[str, Any],
    view_id: str,
) -> tuple[dict[str, Any], set[str]]:
    mandatory, optional = split_rules(filters)
    rules = mandatory + optional
    if not rules:
        return features, set()
    prefixes = ("horizon:", "quality:", "representation:")
    structural = {rule for rule in rules if rule.startswith(prefixes)}
    matched = {rule for rule in structural if _structural_match(rule, row, view_id)}
    if structural - matched:
        return {}, matched
    feature_rules = tuple(rule for rule in rules if rule not in structural)
    if not feature_rules:
        return features, matched
    included: dict[str, Any] = {}
    for feature_id, value in features.items():
        item = metadata.get(feature_id, {})
        for rule in feature_rules:
            if _feature_match(rule, feature_id, item):
                included[feature_id] = value
                matched.add(rule)
    return included, matched


def split_rules(filters: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    mandatory: list[str] = []
    optional: list[str] = []
    for raw in filters:
        rule = raw.strip()
        if not rule or rule in _STRUCTURAL_FILTERS:
            continue
        if rule.startswith("optional:"):
            optional.append(rule[len("optional:"):])
        else:
            mandatory.append(rule)
    return tuple(mandatory), tuple(optional)


def _structural_match(rule: str, row: dict[str, Any], view_id: str) -> bool:
    if rule.startswith("horizon:"):
        return rule[8:] == str(row.get("horizon_group", ""))
    if rule.startswith("quality:"):
        return rule[8:] == str(row.get("quality_state", "PASS"))
    return rule[15:] == view_id


def _feature_match(rule: str, feature_id: str, item: dict[str, Any]) -> bool:
    family = str(item.get("family_id") or "")
    modalities = {str(entry) for entry in item.get("source_modalities", [])}
    return (
        rule == feature_id
        or (rule.startswith("feature:") and rule[8:] == feature_id)
        or (rule.startswith("family:") and rule[7:] == family)
        or (rule.startswith("modality:") and rule[9:] in modalities)
        or rule == family
        or rule in modalities
    )
