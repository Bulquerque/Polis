from __future__ import annotations

from pydantic import model_validator

from .base import ModuleId, NonEmptyStr, PhaseId, SemanticVersion, Sha256Hex, StrictModel


class ModuleBinding(StrictModel):
    module_id: ModuleId
    phase_id: PhaseId
    subphase_id: NonEmptyStr


class ModuleRegistrySnapshot(StrictModel):
    registry_version: SemanticVersion
    registry_sha256: Sha256Hex
    modules: tuple[ModuleBinding, ...]

    @model_validator(mode="after")
    def validate_unique(self) -> "ModuleRegistrySnapshot":
        ids = [item.module_id for item in self.modules]
        if len(ids) != len(set(ids)):
            raise ValueError("module registry IDs must be unique")
        return self

    def contains(self, module_id: str) -> bool:
        return any(item.module_id == module_id for item in self.modules)

    def binding(self, module_id: str) -> ModuleBinding | None:
        return next((item for item in self.modules if item.module_id == module_id), None)


class ArtifactSchemaBinding(StrictModel):
    schema_name: NonEmptyStr
    schema_version: SemanticVersion
    schema_sha256: Sha256Hex
    artifact_type: NonEmptyStr
    allowed_producer_module_ids: tuple[ModuleId, ...]


class ArtifactSchemaRegistrySnapshot(StrictModel):
    registry_version: SemanticVersion
    registry_sha256: Sha256Hex
    bindings: tuple[ArtifactSchemaBinding, ...]

    @model_validator(mode="after")
    def validate_unique(self) -> "ArtifactSchemaRegistrySnapshot":
        keys = [(item.schema_name, item.schema_version) for item in self.bindings]
        if len(keys) != len(set(keys)):
            raise ValueError("schema registry bindings must be unique")
        return self

    def binding(self, schema_name: str, schema_version: str) -> ArtifactSchemaBinding | None:
        return next(
            (
                item
                for item in self.bindings
                if item.schema_name == schema_name and item.schema_version == schema_version
            ),
            None,
        )


class ContractCompatibilityEntry(StrictModel):
    contract_name: NonEmptyStr
    contract_version: SemanticVersion
    accepted_modes: tuple[NonEmptyStr, ...]


class ContractCompatibilityMatrix(StrictModel):
    matrix_version: SemanticVersion
    matrix_sha256: Sha256Hex
    entries: tuple[ContractCompatibilityEntry, ...]

    def supports(self, contract_name: str, contract_version: str, mode: str) -> bool:
        return any(
            item.contract_name == contract_name
            and item.contract_version == contract_version
            and mode in item.accepted_modes
            for item in self.entries
        )
