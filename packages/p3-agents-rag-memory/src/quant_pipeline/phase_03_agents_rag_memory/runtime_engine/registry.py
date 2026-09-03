from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CapabilityRegistration:
    capability_id: str
    module_ids: tuple[str, ...]
    source_packages: tuple[str, ...]
    canonical_outputs: tuple[str, ...]


def _ids(start: int, end: int, module_counts: dict[int, int]) -> tuple[str, ...]:
    return tuple(
        f"P3.S{subphase}.M{module:02d}"
        for subphase in range(start, end + 1)
        for module in range(1, module_counts[subphase] + 1)
    )


MODULE_COUNTS = {
    17: 2,
    18: 2,
    19: 2,
    20: 7,
    21: 6,
    22: 3,
    23: 2,
    24: 3,
    25: 3,
    26: 3,
    27: 3,
    28: 3,
    29: 2,
    30: 5,
    31: 2,
}

CAPABILITIES = (
    CapabilityRegistration(
        capability_id="CONTEXT_STIMULI_CONTEXT",
        module_ids=_ids(17, 20, MODULE_COUNTS),
        source_packages=("s17", "s18", "s19", "s20"),
        canonical_outputs=(
            "person_context_bundle",
            "retrieval_evidence_map",
            "stimulus_panel",
            "activation_panel",
            "person_learning_trajectory_bundle",
        ),
    ),
    CapabilityRegistration(
        capability_id="COGNITION_COGNITION_SOCIAL",
        module_ids=_ids(21, 24, MODULE_COUNTS),
        source_packages=(
            "runtime",
            "runtime_shared.s21_models",
            "runtime_shared.s22_models",
            "runtime_shared.s23_models",
            "runtime_shared.s24_models",
        ),
        canonical_outputs=(
            "belief_update_panel",
            "belief_commitment_log",
            "person_state_delta_panel",
            "social_observation_panel",
        ),
    ),
    CapabilityRegistration(
        capability_id="SOCIETY_EVOLUTION_EMERGENCE",
        module_ids=_ids(25, 28, MODULE_COUNTS),
        source_packages=("s25", "s26", "s27", "s28"),
        canonical_outputs=(
            "cycle_state_snapshot_out",
            "next_cycle_endogenous_stimulus_queue",
            "belief_distribution_panel",
            "society_state_panel",
            "memory_feature_projection",
        ),
    ),
    CapabilityRegistration(
        capability_id="PRODUCTS_PRODUCTS_EXPORTS",
        module_ids=_ids(29, 31, MODULE_COUNTS),
        source_packages=("s29_products", "s30_products", "s31_products"),
        canonical_outputs=(
            "social_feature_panel",
            "evidence_tag_panel",
            "agent_disagreement_panel",
            "context_memory_feature_panel",
            "hypothesis_registry",
            "phase4_social_handoff_manifest",
            "p9_evaluation_evidence_bundle",
            "p9_context_learning_handoff_manifest",
        ),
    ),
)

RUNTIME_MODULE_IDS = tuple(module_id for capability in CAPABILITIES for module_id in capability.module_ids)


def validate_registry() -> None:
    if len(RUNTIME_MODULE_IDS) != 48:
        raise RuntimeError(f"runtime registry must contain 48 modules, found {len(RUNTIME_MODULE_IDS)}")
    if len(set(RUNTIME_MODULE_IDS)) != 48:
        raise RuntimeError("runtime registry contains duplicate module IDs")
    if any(not item.source_packages for item in CAPABILITIES):
        raise RuntimeError("Every capability must name its source packages")


EXECUTION_SLICES = {
    "CONTEXT": _ids(17, 20, MODULE_COUNTS),
    "COGNITION": _ids(21, 24, MODULE_COUNTS),
    "SOCIETY_CLOSURE": _ids(25, 26, MODULE_COUNTS),
    "SOCIETY_ANALYTICS": _ids(27, 28, MODULE_COUNTS),
    "PRODUCTS": _ids(29, 31, MODULE_COUNTS),
}


def module_ids_for_mode(mode: str) -> tuple[str, ...]:
    """Return the only valid execution scope for a Cycle Kernel mode."""

    normalized = mode.upper()
    if normalized == "WARMUP_REPLAY":
        names = ("CONTEXT", "COGNITION", "SOCIETY_CLOSURE")
    elif normalized == "REPLAY":
        names = ("CONTEXT", "COGNITION", "SOCIETY_CLOSURE", "SOCIETY_ANALYTICS")
    elif normalized == "LIVE":
        names = ("CONTEXT", "COGNITION", "SOCIETY_CLOSURE", "SOCIETY_ANALYTICS", "PRODUCTS")
    elif normalized == "DRY_RUN":
        return ()
    else:
        raise ValueError(f"unsupported execution mode: {mode}")
    return tuple(module_id for name in names for module_id in EXECUTION_SLICES[name])
