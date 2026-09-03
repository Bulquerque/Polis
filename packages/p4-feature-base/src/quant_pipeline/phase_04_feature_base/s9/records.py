from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DriftPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    reference_timestamps: int = Field(ge=2)
    current_timestamps: int = Field(ge=1)
    min_samples: int = Field(ge=2)
    ks_warn: float = Field(ge=0, le=1)
    ks_block: float = Field(ge=0, le=1)
    ks_significance_alpha: float = Field(gt=0, le=1)
    normalized_wasserstein_warn: float = Field(ge=0)
    normalized_wasserstein_block: float = Field(ge=0)
    missingness_delta_warn: float = Field(ge=0, le=1)
    missingness_delta_block: float = Field(ge=0, le=1)
    loading_drift_warn: float = Field(ge=0, le=2)
    loading_drift_block: float = Field(ge=0, le=2)
    reconstruction_delta_warn: float = Field(ge=0)
    reconstruction_delta_block: float = Field(ge=0)
    reconstruction_error_floor: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_ordering(self) -> "DriftPolicy":
        ordered = (
            (self.ks_warn, self.ks_block, "ks"),
            (
                self.normalized_wasserstein_warn,
                self.normalized_wasserstein_block,
                "wasserstein",
            ),
            (self.missingness_delta_warn, self.missingness_delta_block, "missingness"),
            (self.loading_drift_warn, self.loading_drift_block, "loading"),
            (
                self.reconstruction_delta_warn,
                self.reconstruction_delta_block,
                "reconstruction",
            ),
        )
        for warn, block, name in ordered:
            if warn > block:
                raise ValueError(f"{name} warn threshold exceeds block threshold")
        return self


class ConsumerViewPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled_views: tuple[
        Literal[
            "TABULAR_INTERPRETABLE",
            "CROSS_SECTIONAL_RANKED",
            "SEQUENCE_MULTI_HORIZON",
            "GRAPH_RELATIONAL",
            "TAIL_RISK_SPECIALIST",
            "REGIME_CONTEXT",
            "LATENT_FAMILY",
            "SPARSE_MODALITY_AWARE",
        ],
        ...,
    ]
    materialize_payloads: bool = False

    @model_validator(mode="after")
    def validate_unique_views(self) -> "ConsumerViewPolicy":
        if len(self.enabled_views) != len(set(self.enabled_views)):
            raise ValueError("enabled consumer views must be unique")
        return self


class ResearchBudgetPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    expected_foundational_hypotheses: int = Field(ge=1)
    max_parameterizations_per_hypothesis: int = Field(ge=1)
    max_encoder_configurations: int = Field(ge=0)
    require_negative_results: bool = True


class FamilyCoveragePolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    expected_family_ids: tuple[str, ...]
    required_family_ids: tuple[str, ...]
    registered_family_ids: tuple[str, ...] = ()
    min_selected_features_per_family: int = Field(ge=1)
    strict_complete_handoff: bool = True

    @model_validator(mode="after")
    def validate_families(self) -> "FamilyCoveragePolicy":
        if len(self.expected_family_ids) != len(set(self.expected_family_ids)):
            raise ValueError("expected family IDs must be unique")
        if len(self.required_family_ids) != len(set(self.required_family_ids)):
            raise ValueError("required family IDs must be unique")
        unknown = set(self.required_family_ids) - set(self.expected_family_ids)
        if unknown:
            raise ValueError(f"required family IDs are not expected: {sorted(unknown)}")
        registered = set(self.registered_family_ids) or set(self.expected_family_ids)
        unknown_required = set(self.required_family_ids) - registered
        if unknown_required:
            raise ValueError(
                f"required family IDs are not registered: {sorted(unknown_required)}"
            )
        return self


class S9Policy(BaseModel):
    model_config = ConfigDict(frozen=True)

    drift: DriftPolicy
    consumer_views: ConsumerViewPolicy
    research_budget: ResearchBudgetPolicy
    family_coverage: FamilyCoveragePolicy
    max_warn_records_before_degradation: int = Field(ge=0)
    max_block_records_before_handoff_block: int = Field(ge=0)
