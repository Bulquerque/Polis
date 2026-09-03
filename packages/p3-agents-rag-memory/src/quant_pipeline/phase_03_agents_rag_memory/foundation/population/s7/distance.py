"""Pure, versioned mixed-profile distance and clone detection."""
from __future__ import annotations

from itertools import combinations
import math

from .hashing import sha256_hex
from .models import (
    CandidateProposal,
    ExactCloneGroup,
    FrozenPerson,
    NearClonePair,
    PopulationRepresentationConfig,
)


def profile_fingerprint(profile: CandidateProposal, *, digits: int) -> str:
    return sha256_hex(profile.model_dump(mode="json"), float_digits=digits)


def _categorical_distance(left: CandidateProposal, right: CandidateProposal) -> float:
    fields = (
        "life_stage",
        "occupation_family",
        "economic_role",
        "role_family",
        "institution_type",
        "geography",
        "education_level",
    )
    mismatches = sum(getattr(left, field) != getattr(right, field) for field in fields)
    return mismatches / len(fields)


def _jaccard_distance(left: tuple[str, ...], right: tuple[str, ...]) -> float:
    union = set(left) | set(right)
    return 0.0 if not union else 1.0 - len(set(left) & set(right)) / len(union)


def _resources_distance(left: CandidateProposal, right: CandidateProposal) -> float:
    numeric = [
        abs(left.resources.information_access - right.resources.information_access),
        abs(left.resources.research_time - right.resources.research_time),
        abs(left.resources.computational_access - right.resources.computational_access),
    ]
    return math.fsum([*numeric, _jaccard_distance(left.resources.flags, right.resources.flags)]) / 4.0


def _capabilities_distance(left: CandidateProposal, right: CandidateProposal) -> float:
    fields = ("research", "quantitative", "verbal", "coding", "tool_use")
    return math.fsum(
        abs(getattr(left.capabilities, field) - getattr(right.capabilities, field))
        for field in fields
    ) / len(fields)


def _mapping_l1_distance(left: dict[str, float], right: dict[str, float]) -> float:
    keys = sorted(set(left) | set(right))
    return 0.0 if not keys else math.fsum(abs(left.get(key, 0.0) - right.get(key, 0.0)) for key in keys) / len(keys)


def _objectives_distance(left: CandidateProposal, right: CandidateProposal) -> float:
    return _mapping_l1_distance(
        {item.objective_id: item.weight for item in left.objective_weights},
        {item.objective_id: item.weight for item in right.objective_weights},
    )


def _tags_distance(left: CandidateProposal, right: CandidateProposal) -> float:
    return _mapping_l1_distance(
        {item.tag_id: item.intensity * item.confidence for item in left.tags},
        {item.tag_id: item.intensity * item.confidence for item in right.tags},
    )


def profile_distance(
    left: CandidateProposal,
    right: CandidateProposal,
    config: PopulationRepresentationConfig,
) -> float:
    weights = config.distance_weights
    return math.fsum(
        (
            weights.categorical * _categorical_distance(left, right),
            weights.resources * _resources_distance(left, right),
            weights.capabilities * _capabilities_distance(left, right),
            weights.objectives * _objectives_distance(left, right),
            weights.tags * _tags_distance(left, right),
        )
    )


def detect_clones(
    persons: tuple[FrozenPerson, ...],
    config: PopulationRepresentationConfig,
) -> tuple[tuple[ExactCloneGroup, ...], tuple[NearClonePair, ...], float]:
    grouped: dict[str, list[str]] = {}
    for person in persons:
        grouped.setdefault(person.profile_fingerprint, []).append(person.person_id)
    exact = tuple(
        ExactCloneGroup(profile_fingerprint=fingerprint, person_ids=tuple(sorted(person_ids)))
        for fingerprint, person_ids in sorted(grouped.items())
        if len(person_ids) > 1
    )
    exact_pairs = {
        tuple(sorted((left, right)))
        for group in exact
        for left, right in combinations(group.person_ids, 2)
    }
    near: list[NearClonePair] = []
    involved: set[str] = set()
    for left, right in combinations(sorted(persons, key=lambda item: item.person_id), 2):
        key = tuple(sorted((left.person_id, right.person_id)))
        if key in exact_pairs:
            continue
        distance = profile_distance(left.profile, right.profile, config)
        if distance <= config.near_clone_distance_threshold:
            near.append(
                NearClonePair(
                    left_person_id=left.person_id,
                    right_person_id=right.person_id,
                    distance=round(distance, config.profile_numeric_precision),
                )
            )
            involved.update(key)
    share = 0.0 if not persons else len(involved) / len(persons)
    return exact, tuple(near), share
