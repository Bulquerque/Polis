"""Executable module-contract authority for 81 legacy + 47 extension modules.

The canonical documents are vendored as package assets so an installed wheel and a
source checkout enforce the same inputs, outputs and artifact schemas.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError


class ModuleContractError(ValueError):
    """A module invocation or result violated the declared P3 contract."""


@dataclass(frozen=True, slots=True)
class ModuleContract:
    module_id: str
    required_inputs: tuple[str, ...]
    optional_inputs: tuple[str, ...]
    produced_outputs: tuple[str, ...]

    @property
    def accepted_inputs(self) -> tuple[str, ...]:
        return self.required_inputs + self.optional_inputs


@dataclass(frozen=True, slots=True)
class SchemaBinding:
    artifact_name: str
    relative_path: str
    schema: Mapping[str, Any]
    sha256: str


@lru_cache(maxsize=1)
def _matrix() -> Mapping[str, ModuleContract]:
    root = files("quant_pipeline.phase_03_agents_rag_memory.assets")
    document = yaml.safe_load(root.joinpath("contracts/MODULE_IO_MATRIX.yaml").read_text(encoding="utf-8"))
    contracts: dict[str, ModuleContract] = {}
    for row in document["module_io_matrix"]:
        contracts[str(row["module_id"])] = ModuleContract(
            module_id=str(row["module_id"]),
            required_inputs=tuple(str(item) for item in row["consumes_from"]["artifacts"]),
            optional_inputs=(),
            produced_outputs=tuple(str(item) for item in row["emits_to"]["artifacts"]),
        )

    from .extension_authority import extension_io_rows

    for row in extension_io_rows():
        all_inputs = tuple(str(item) for item in row.get("inputs", ()))
        optional = tuple(str(item) for item in row.get("optional_inputs", ()))
        required = tuple(item for item in all_inputs if item not in set(optional))
        contracts[str(row["module_id"])] = ModuleContract(
            module_id=str(row["module_id"]),
            required_inputs=required,
            optional_inputs=optional,
            produced_outputs=tuple(str(item) for item in row.get("outputs", ())),
        )
    if len(contracts) != 128:
        raise RuntimeError(f"module contract authority contains {len(contracts)} modules; expected 128")
    return contracts


@lru_cache(maxsize=1)
def _bindings() -> Mapping[str, SchemaBinding]:
    root = files("quant_pipeline.phase_03_agents_rag_memory.assets")
    document = yaml.safe_load(root.joinpath("contracts/ARTIFACT_SCHEMA_BINDINGS.yaml").read_text(encoding="utf-8"))
    result: dict[str, SchemaBinding] = {}
    for row in document["bindings"]:
        name = str(row["artifact"])
        relative = str(row["schema"]).removeprefix("schemas/")
        resource = root.joinpath("schemas", relative)
        raw = resource.read_bytes()
        schema = json.loads(raw) if relative.endswith(".json") else yaml.safe_load(raw.decode("utf-8"))
        if not isinstance(schema, Mapping):
            raise RuntimeError(f"schema for {name} must be a mapping")
        result[name] = SchemaBinding(
            artifact_name=name,
            relative_path=relative,
            schema=dict(schema),
            sha256=hashlib.sha256(raw).hexdigest(),
        )
    return result


def contract_for(module_id: str) -> ModuleContract:
    try:
        return _matrix()[module_id]
    except KeyError as exc:
        raise ModuleContractError(f"unknown module contract: {module_id}") from exc


def schema_binding_for(artifact_name: str) -> SchemaBinding | None:
    return _bindings().get(artifact_name)


def _validate_required_fields(payload: Mapping[str, Any], schema: Mapping[str, Any], *, label: str) -> None:
    required = schema.get("required_fields")
    if isinstance(required, list):
        missing = sorted(str(item) for item in required if str(item) not in payload)
        if missing:
            raise ModuleContractError(f"{label} is missing required_fields: {missing}")


def validate_artifact_payload(artifact_name: str, payload: Mapping[str, Any]) -> None:
    binding = schema_binding_for(artifact_name)
    if binding is None:
        return
    schema = binding.schema
    _validate_required_fields(payload, schema, label=artifact_name)
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(dict(payload))
    except SchemaError as exc:
        raise ModuleContractError(f"invalid schema authority for {artifact_name}: {exc.message}") from exc
    except ValidationError as exc:
        path = ".".join(str(item) for item in exc.absolute_path) or "root"
        raise ModuleContractError(f"{artifact_name} schema violation at {path}: {exc.message}") from exc


def validate_module_inputs(
    module_id: str,
    inputs: Mapping[str, Any],
    *,
    allow_extra: bool = False,
    validate_payloads: bool = True,
) -> None:
    contract = contract_for(module_id)
    actual = set(inputs)
    required = set(contract.required_inputs)
    accepted = set(contract.accepted_inputs)
    missing = sorted(required - actual)
    extra = sorted(actual - accepted)
    if missing:
        raise ModuleContractError(f"{module_id} missing required inputs: {missing}")
    if extra and not allow_extra:
        raise ModuleContractError(f"{module_id} received undeclared inputs: {extra}")
    if validate_payloads:
        for name in contract.accepted_inputs:
            if name not in inputs:
                continue
            value = inputs[name]
            if isinstance(value, Mapping):
                validate_artifact_payload(name, value)


def validate_module_outputs(
    module_id: str,
    outputs: Mapping[str, Any],
    *,
    validate_payloads: bool = True,
) -> None:
    contract = contract_for(module_id)
    actual = set(outputs)
    expected = set(contract.produced_outputs)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise ModuleContractError(
            f"{module_id} output set mismatch; missing={missing}, undeclared={extra}, expected={sorted(expected)}"
        )
    if validate_payloads:
        for name in contract.produced_outputs:
            value = outputs[name]
            if not isinstance(value, Mapping):
                raise ModuleContractError(f"{module_id} output {name} must be a mapping")
            validate_artifact_payload(name, value)


def validate_declared_module_metadata(module_id: str, module: object) -> None:
    contract = contract_for(module_id)
    declared_inputs = tuple(str(item) for item in getattr(module, "REQUIRED_INPUTS", ()))
    declared_optional_inputs = tuple(str(item) for item in getattr(module, "OPTIONAL_INPUTS", ()))
    declared_outputs = tuple(str(item) for item in getattr(module, "PRODUCED_OUTPUTS", ()))
    if declared_inputs != contract.required_inputs:
        raise ModuleContractError(
            f"{module_id} REQUIRED_INPUTS mismatch: declared={declared_inputs}, contract={contract.required_inputs}"
        )
    if declared_optional_inputs != contract.optional_inputs:
        raise ModuleContractError(
            f"{module_id} OPTIONAL_INPUTS mismatch: declared={declared_optional_inputs}, contract={contract.optional_inputs}"
        )
    overlap = sorted(set(declared_inputs) & set(declared_optional_inputs))
    if overlap:
        raise ModuleContractError(f"{module_id} declares inputs as both required and optional: {overlap}")
    if declared_outputs != contract.produced_outputs:
        raise ModuleContractError(
            f"{module_id} PRODUCED_OUTPUTS mismatch: declared={declared_outputs}, contract={contract.produced_outputs}"
        )
    if not callable(getattr(module, "execute", None)):
        raise ModuleContractError(f"{module_id} has no canonical execute(inputs, context)")


__all__ = [
    "ModuleContract",
    "ModuleContractError",
    "SchemaBinding",
    "contract_for",
    "schema_binding_for",
    "validate_artifact_payload",
    "validate_declared_module_metadata",
    "validate_module_inputs",
    "validate_module_outputs",
]
