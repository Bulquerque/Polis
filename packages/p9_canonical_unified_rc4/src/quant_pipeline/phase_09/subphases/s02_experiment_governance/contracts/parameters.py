from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from pydantic import Field, model_validator

from .base import (
    CapabilityId,
    CapabilityState,
    ModuleId,
    NonEmptyStr,
    ParameterId,
    ParameterKind,
    ParameterScale,
    RegistryState,
    ReasonCode,
    SemanticVersion,
    Sha256Hex,
    StrictModel,
)
from .experiment import ValidatedExperimentSpecification

ParameterScalar = int | float | bool | str


class ParameterCondition(StrictModel):
    parent_parameter_id: ParameterId
    operator: str
    values: tuple[ParameterScalar, ...]

    @model_validator(mode="after")
    def validate_values(self) -> "ParameterCondition":
        if self.operator not in {"EQUALS", "NOT_EQUALS", "IN", "NOT_IN"}:
            raise ValueError("unsupported parameter condition operator")
        if not self.values:
            raise ValueError("parameter condition values must not be empty")
        return self


class HyperparameterDefinition(StrictModel):
    parameter_id: ParameterId
    schema_version: SemanticVersion
    owner_module_id: ModuleId
    capability_id: CapabilityId | None = None
    kind: ParameterKind
    scale: ParameterScale = ParameterScale.LINEAR
    unit: NonEmptyStr | None = None
    lower: int | float | None = None
    upper: int | float | None = None
    choices: tuple[ParameterScalar, ...] = ()
    default: ParameterScalar
    active_when: tuple[ParameterCondition, ...] = ()
    aliases: tuple[ParameterId, ...] = ()
    deprecated: bool = False
    replacement_parameter_id: ParameterId | None = None
    economic_description: NonEmptyStr

    @model_validator(mode="after")
    def validate_definition(self) -> "HyperparameterDefinition":
        if self.owner_module_id.split(".", 1)[0] != self.parameter_id.split(".", 1)[0]:
            raise ValueError("parameter owner phase must match parameter namespace")
        if self.kind in {ParameterKind.INTEGER, ParameterKind.FLOAT}:
            if self.lower is None or self.upper is None:
                raise ValueError("numeric parameter requires lower and upper bounds")
            if self.lower >= self.upper:
                raise ValueError("parameter lower bound must be < upper bound")
            if self.choices:
                raise ValueError("numeric parameter cannot define choices")
            if self.scale is ParameterScale.LOG and self.lower <= 0:
                raise ValueError("log-scale parameter requires positive lower bound")
            if isinstance(self.default, bool) or not isinstance(self.default, (int, float)):
                raise ValueError("numeric parameter default must be numeric")
            if not self.lower <= self.default <= self.upper:
                raise ValueError("numeric parameter default must be inside bounds")
            if self.kind is ParameterKind.INTEGER and not isinstance(self.default, int):
                raise ValueError("integer parameter default must be int")
        elif self.kind is ParameterKind.CATEGORICAL:
            if not self.choices:
                raise ValueError("categorical parameter requires choices")
            if self.lower is not None or self.upper is not None:
                raise ValueError("categorical parameter cannot define numeric bounds")
            if self.default not in self.choices:
                raise ValueError("categorical default must be one of choices")
        elif self.kind is ParameterKind.BOOLEAN:
            if self.lower is not None or self.upper is not None or self.choices:
                raise ValueError("boolean parameter cannot define bounds or choices")
            if not isinstance(self.default, bool):
                raise ValueError("boolean parameter default must be bool")
        if len(set(self.aliases)) != len(self.aliases):
            raise ValueError("parameter aliases must be unique")
        if self.parameter_id in self.aliases:
            raise ValueError("parameter cannot alias itself")
        if self.deprecated and self.replacement_parameter_id is None:
            raise ValueError("deprecated parameter requires replacement")
        if not self.deprecated and self.replacement_parameter_id is not None:
            raise ValueError("non-deprecated parameter cannot define replacement")
        return self


class PhaseParameterContractSnapshot(StrictModel):
    phase_id: NonEmptyStr
    contract_version: SemanticVersion
    contract_sha256: Sha256Hex
    capability_state: CapabilityState
    parameters: tuple[HyperparameterDefinition, ...]

    @model_validator(mode="after")
    def validate_phase(self) -> "PhaseParameterContractSnapshot":
        if self.phase_id not in {"P5", "P6", "P7", "P8"}:
            raise ValueError("phase parameter contracts are limited to P5-P8")
        for parameter in self.parameters:
            if parameter.parameter_id.split(".", 1)[0] != self.phase_id:
                raise ValueError("parameter namespace must match phase contract")
        return self


class PhaseParameterContractSnapshots(StrictModel):
    snapshots: tuple[PhaseParameterContractSnapshot, ...]

    @model_validator(mode="after")
    def validate_unique_phases(self) -> "PhaseParameterContractSnapshots":
        phases = [snapshot.phase_id for snapshot in self.snapshots]
        if len(phases) != len(set(phases)):
            raise ValueError("phase parameter snapshots must be unique by phase")
        return self


class DeprecationEntry(StrictModel):
    deprecated_parameter_id: ParameterId
    replacement_parameter_id: ParameterId
    removal_after_version: SemanticVersion
    migration_note: NonEmptyStr


class DeprecationRegistry(StrictModel):
    registry_version: SemanticVersion
    registry_sha256: Sha256Hex
    entries: tuple[DeprecationEntry, ...] = ()


class HyperparameterSchemaSnapshot(StrictModel):
    snapshot_id: NonEmptyStr
    experiment_id: NonEmptyStr
    snapshot_sha256: Sha256Hex
    definitions: tuple[HyperparameterDefinition, ...]

    @model_validator(mode="after")
    def validate_unique(self) -> "HyperparameterSchemaSnapshot":
        ids = [definition.parameter_id for definition in self.definitions]
        if len(ids) != len(set(ids)):
            raise ValueError("parameter definitions must have unique IDs")
        aliases = [alias for definition in self.definitions for alias in definition.aliases]
        if len(aliases) != len(set(aliases)):
            raise ValueError("parameter aliases must be globally unique")
        if set(ids) & set(aliases):
            raise ValueError("alias cannot collide with canonical parameter ID")
        return self

    def definition(self, parameter_id: str) -> HyperparameterDefinition | None:
        direct = next(
            (
                definition
                for definition in self.definitions
                if definition.parameter_id == parameter_id
            ),
            None,
        )
        if direct is not None:
            return direct
        return next(
            (definition for definition in self.definitions if parameter_id in definition.aliases),
            None,
        )

    def canonical_ids(self) -> tuple[str, ...]:
        return tuple(definition.parameter_id for definition in self.definitions)


class ParameterCompatibilityIssue(StrictModel):
    parameter_id: NonEmptyStr
    reason_code: ReasonCode
    description: NonEmptyStr
    blocking: bool


class ParameterCompatibilityReport(StrictModel):
    state: RegistryState
    issues: tuple[ParameterCompatibilityIssue, ...] = ()
    reason_codes: tuple[ReasonCode, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_report(self) -> "ParameterCompatibilityReport":
        blocking_states = {
            RegistryState.PARAMETER_SCHEMA_INCOMPATIBLE,
            RegistryState.PARAMETER_DEPRECATED_BLOCKING,
        }
        if self.state in blocking_states and not self.reason_codes:
            raise ValueError("blocking registry state requires reason codes")
        return self


class ParameterAuthorityBinding(StrictModel):
    parameter_id: ParameterId
    owner_module_id: ModuleId
    capability_id: CapabilityId | None
    capability_state: CapabilityState


class ParameterAuthorityMap(StrictModel):
    bindings: tuple[ParameterAuthorityBinding, ...]

    @model_validator(mode="after")
    def validate_unique(self) -> "ParameterAuthorityMap":
        ids = [binding.parameter_id for binding in self.bindings]
        if len(ids) != len(set(ids)):
            raise ValueError("authority bindings must be unique")
        return self


class HyperparameterRegistryInput(StrictModel):
    validated_specification: ValidatedExperimentSpecification
    phase_contracts: PhaseParameterContractSnapshots
    deprecations: DeprecationRegistry


def unique_parameter_ids(
    snapshots: Iterable[PhaseParameterContractSnapshot],
) -> tuple[str, ...]:
    return tuple(
        parameter.parameter_id
        for snapshot in snapshots
        for parameter in snapshot.parameters
    )


class HyperparameterRegistryOutcome(StrictModel):
    snapshot: HyperparameterSchemaSnapshot | None
    compatibility_report: ParameterCompatibilityReport
    authority_map: ParameterAuthorityMap | None
