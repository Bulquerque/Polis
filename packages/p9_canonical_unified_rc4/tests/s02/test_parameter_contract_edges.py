from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from quant_pipeline.phase_09.subphases.s02_experiment_governance.contracts.parameters import (
    HyperparameterDefinition,
    ParameterCondition,
)

BASE = {
    "parameter_id": "P5.model.alpha",
    "schema_version": "1.0.0",
    "owner_module_id": "P5.S1.M01",
    "capability_id": None,
    "kind": "FLOAT",
    "scale": "LINEAR",
    "unit": None,
    "lower": 0.0,
    "upper": 1.0,
    "choices": [],
    "default": 0.5,
    "active_when": [],
    "aliases": [],
    "deprecated": False,
    "replacement_parameter_id": None,
    "economic_description": "test parameter",
}


def rejected(**updates) -> None:
    raw = dict(BASE)
    raw.update(updates)
    with pytest.raises(ValidationError):
        HyperparameterDefinition.model_validate_json(json.dumps(raw))


def test_numeric_contract_rejections() -> None:
    rejected(lower=None)
    rejected(lower=1.0, upper=1.0)
    rejected(choices=[0.5])
    rejected(scale="LOG", lower=0.0)
    rejected(default=True)
    rejected(default=2.0)
    rejected(kind="INTEGER", lower=0, upper=3, default=1.5)


def test_categorical_and_boolean_rejections() -> None:
    rejected(kind="CATEGORICAL", lower=None, upper=None, choices=[], default="A")
    rejected(kind="CATEGORICAL", lower=None, upper=None, choices=["A"], default="B")
    rejected(kind="BOOLEAN", lower=None, upper=None, choices=[True, False], default=True)
    rejected(kind="BOOLEAN", lower=None, upper=None, choices=[], default="true")


def test_alias_and_deprecation_rejections() -> None:
    rejected(aliases=["P5.legacy.alpha", "P5.legacy.alpha"])
    rejected(aliases=["P5.model.alpha"])
    rejected(deprecated=True, replacement_parameter_id=None)
    rejected(deprecated=False, replacement_parameter_id="P5.model.beta")
    rejected(owner_module_id="P6.S1.M01")


def test_parameter_condition_validation() -> None:
    with pytest.raises(ValidationError):
        ParameterCondition(
            parent_parameter_id="P5.model.alpha",
            operator="UNKNOWN",
            values=(1,),
        )
    with pytest.raises(ValidationError):
        ParameterCondition(
            parent_parameter_id="P5.model.alpha",
            operator="EQUALS",
            values=(),
        )
