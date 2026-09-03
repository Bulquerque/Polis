"""Declarative model/view bindings used by S2 without hardcoded resolver specs."""
from __future__ import annotations

from ..domain.training import ModelBinding
from ..domain.v2_base import CapabilityStatus


MODEL_BINDINGS: tuple[ModelBinding, ...] = (
    ModelBinding(
        binding_id="baseline-mean-v1", resolver_family="BASELINE", implementation_id="builtin.mean",
        target_families=("RETURN", "DIRECTION", "VOLATILITY", "TAIL", "PATH_RISK"),
        compatible_views=("TABULAR_INTERPRETABLE",), minimum_sample=16,
        resource_budget={"max_seconds": 5, "max_memory_mb": 128},
        capability_status=CapabilityStatus.AVAILABLE, role="RESERVE",
    ),
    ModelBinding(
        binding_id="robust-ridge-v1", resolver_family="LINEAR", implementation_id="builtin.ridge",
        target_families=("RETURN", "DIRECTION", "VOLATILITY", "TAIL", "PATH_RISK"),
        compatible_views=("TABULAR_INTERPRETABLE", "CROSS_SECTIONAL_RANKED", "SPARSE_MODALITY_AWARE"),
        minimum_sample=24, resource_budget={"max_seconds": 10, "max_memory_mb": 256},
        capability_status=CapabilityStatus.AVAILABLE, role="CORE", parameters={"alpha": 1.0},
    ),
    ModelBinding(
        binding_id="huber-irls-v1", resolver_family="ROBUST_LINEAR", implementation_id="builtin.huber_irls",
        target_families=("RETURN", "VOLATILITY", "TAIL", "PATH_RISK"),
        compatible_views=("TABULAR_INTERPRETABLE", "SPARSE_MODALITY_AWARE"), minimum_sample=24,
        resource_budget={"max_seconds": 15, "max_memory_mb": 256},
        capability_status=CapabilityStatus.AVAILABLE, role="CHALLENGER",
        parameters={"delta": 1.345, "ridge": 0.0001, "max_iter": 40},
    ),
    ModelBinding(
        binding_id="kalman-dlm-v1", resolver_family="STATE_SPACE", implementation_id="builtin.kalman_dlm",
        target_families=("RETURN", "VOLATILITY"), compatible_views=("TABULAR_INTERPRETABLE",),
        minimum_sample=32, resource_budget={"max_seconds": 15, "max_memory_mb": 256},
        capability_status=CapabilityStatus.AVAILABLE, role="CHALLENGER",
        parameters={"process_scale": 0.0001, "observation_scale": 0.001, "ridge": 1.0},
    ),
    ModelBinding(
        binding_id="histogram-boosting-v1", resolver_family="TREE", implementation_id="builtin.histogram_gradient_boosting",
        target_families=("RETURN", "DIRECTION", "VOLATILITY", "TAIL", "PATH_RISK"),
        compatible_views=("TABULAR_INTERPRETABLE", "CROSS_SECTIONAL_RANKED"), minimum_sample=40,
        resource_budget={"max_seconds": 30, "max_memory_mb": 512},
        capability_status=CapabilityStatus.AVAILABLE, role="CHALLENGER",
        parameters={"max_iter": 25, "max_leaf_nodes": 15, "learning_rate": 0.05},
    ),
    ModelBinding(
        binding_id="extra-trees-v1", resolver_family="TREE", implementation_id="builtin.extra_trees",
        target_families=("RETURN", "DIRECTION", "VOLATILITY", "TAIL", "PATH_RISK"),
        compatible_views=("TABULAR_INTERPRETABLE", "CROSS_SECTIONAL_RANKED"), minimum_sample=40,
        resource_budget={"max_seconds": 30, "max_memory_mb": 512},
        capability_status=CapabilityStatus.AVAILABLE, role="CHALLENGER",
        parameters={"n_estimators": 20, "max_depth": 6, "min_samples_leaf": 3},
    ),
    ModelBinding(
        binding_id="kernel-ridge-v1", resolver_family="KERNEL", implementation_id="builtin.kernel_ridge_rbf",
        target_families=("RETURN", "VOLATILITY"), compatible_views=("TABULAR_INTERPRETABLE",),
        minimum_sample=24, resource_budget={"max_seconds": 20, "max_memory_mb": 384},
        capability_status=CapabilityStatus.AVAILABLE, role="CHALLENGER",
        parameters={"alpha": 1.0, "gamma": 0.25, "max_dictionary": 128},
    ),
    ModelBinding(
        binding_id="temporal-neural-port-v1", resolver_family="TEMPORAL_NEURAL",
        implementation_id="optional.temporal_neural", target_families=("RETURN", "VOLATILITY"),
        compatible_views=("SEQUENCE_MULTI_HORIZON",), minimum_sample=128,
        resource_budget={"max_seconds": 300, "max_memory_mb": 2048},
        capability_status=CapabilityStatus.SKIPPED_CAPABILITY_UNAVAILABLE, role="SHADOW",
    ),
    ModelBinding(
        binding_id="foundation-prior-port-v1", resolver_family="FOUNDATION",
        implementation_id="optional.foundation_prior", target_families=("RETURN",),
        compatible_views=("SEQUENCE_MULTI_HORIZON", "LATENT_FAMILY"), minimum_sample=128,
        resource_budget={"max_seconds": 300, "max_memory_mb": 2048},
        capability_status=CapabilityStatus.SKIPPED_CAPABILITY_UNAVAILABLE, role="SHADOW",
    ),
)
