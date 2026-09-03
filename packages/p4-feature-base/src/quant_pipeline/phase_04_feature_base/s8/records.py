from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class EncoderConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True)
    config_id: str
    bottleneck_ratio: float = Field(gt=0, le=1)
    corruption_rate: float = Field(ge=0, lt=1)
    modality_dropout: float = Field(ge=0, lt=1)

class RepresentationPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)
    fold_mode: Literal["expanding", "rolling"] = "expanding"
    min_train_timestamps: int = Field(ge=3)
    validation_timestamps: int = Field(ge=1)
    step_timestamps: int = Field(ge=1)
    max_outer_folds: int = Field(ge=1)
    rolling_train_timestamps: int | None = Field(default=None, ge=3)
    min_train_rows: int = Field(ge=4)
    min_features: int = Field(ge=2)
    pca_variance_threshold: float = Field(gt=0, le=1)
    max_components: int = Field(ge=1)
    sparse_pca_enabled: bool
    sparse_alpha: float = Field(gt=0)
    sparse_ridge_alpha: float = Field(gt=0)
    sparse_max_iter: int = Field(ge=1, le=2000)
    sparse_tol: float = Field(gt=0)
    random_state: int
    encoder_requested: bool
    encoder_min_train_rows: int = Field(ge=4)
    encoder_min_modalities: int = Field(ge=1)
    encoder_max_epochs: int = Field(ge=1, le=500)
    encoder_patience: int = Field(ge=1, le=100)
    encoder_learning_rate: float = Field(gt=0)
    encoder_weight_decay: float = Field(ge=0)
    encoder_huber_delta: float = Field(gt=0)
    encoder_configurations: tuple[EncoderConfiguration, ...]

    @model_validator(mode="after")
    def validate_policy(self) -> "RepresentationPolicy":
        if self.fold_mode == "rolling" and self.rolling_train_timestamps is None:
            raise ValueError("rolling folds require rolling_train_timestamps")
        if len(self.encoder_configurations) != 2:
            raise ValueError("exactly two encoder configurations are permitted")
        if len({item.config_id for item in self.encoder_configurations}) != 2:
            raise ValueError("encoder configuration IDs must be unique")
        return self
