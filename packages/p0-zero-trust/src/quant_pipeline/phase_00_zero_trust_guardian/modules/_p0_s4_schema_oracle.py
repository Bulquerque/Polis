from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib

from ._module_executor import ContractValidationError
from ._p0_s4_test_evidence import load_schema, validate


def load_registered_schemas(entries: list[dict[str, Any]], repository: Path) -> dict[str, dict[str, Any]]:
    by_id = {}
    repository = repository.resolve()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not isinstance(entry.get("schema_id"), str) or not isinstance(entry.get("path"), str):
            raise ContractValidationError(f"schema registry entry {index} is malformed")
        schema_id = entry["schema_id"]
        if schema_id in by_id:
            raise ContractValidationError(f"duplicate schema_id: {schema_id}")
        path = (repository / entry["path"]).resolve()
        try:
            path.relative_to(repository)
        except ValueError as exc:
            raise ContractValidationError("schema path escapes repository") from exc
        schema = load_schema(path)
        expected_hash = entry.get("sha256")
        if expected_hash:
            actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            if expected_hash != actual_hash:
                raise ContractValidationError(f"schema hash mismatch: {schema_id}")
        by_id[schema_id] = schema
    return by_id


def execute_fixture_cases(fixtures: list[dict[str, Any]], schemas: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, set[str]], dict[str, set[str]]]:
    cases = []
    expectations = {schema_id: set() for schema_id in schemas}
    mutations = {schema_id: set() for schema_id in schemas}
    fixture_ids: set[str] = set()
    for index, fixture in enumerate(fixtures):
        if not isinstance(fixture, dict) or not {"fixture_id", "schema_id", "expectation", "payload"}.issubset(fixture):
            raise ContractValidationError(f"fixture {index} is malformed")
        fixture_id = fixture["fixture_id"]
        schema_id = fixture["schema_id"]
        expectation = fixture["expectation"]
        if not isinstance(fixture_id, str) or not fixture_id or fixture_id in fixture_ids:
            raise ContractValidationError("fixture_id values must be non-empty and unique")
        fixture_ids.add(fixture_id)
        if schema_id not in schemas or expectation not in {"valid", "invalid"}:
            raise ContractValidationError(f"fixture {fixture_id} has unknown schema or expectation")
        mutation_class = str(fixture.get("mutation_class", "baseline_invalid" if expectation == "invalid" else "baseline_valid"))
        expectations[schema_id].add(expectation)
        mutations[schema_id].add(mutation_class)
        accepted = True
        diagnostic = ""
        try:
            validate(fixture["payload"], schemas[schema_id], f"fixture:{fixture_id}")
        except ContractValidationError as exc:
            accepted = False
            diagnostic = str(exc)
        passed = accepted if expectation == "valid" else not accepted
        cases.append({
            "fixture_id": fixture_id,
            "schema_id": schema_id,
            "expectation": expectation,
            "mutation_class": mutation_class,
            "validator_accepted": accepted,
            "status": "PASS" if passed else "FAIL",
            "diagnostic": diagnostic,
        })
    return cases, expectations, mutations
