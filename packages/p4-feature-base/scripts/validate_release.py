#!/usr/bin/env python3
from __future__ import annotations

import ast
import csv
import hashlib
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PHASE = ROOT / "src" / "quant_pipeline" / "phase_04_feature_base"
HARD_FILE_LINES = 350
HARD_FUNCTION_LINES = 60
HARD_CLASS_LINES = 180
HARD_WRAPPER_FILE_LINES = 60
HARD_WRAPPER_FUNCTION_LINES = 40
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".hypothesis", "htmlcov", "build", "dist"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
LEGACY_COMPATIBILITY_ALIASES = {"P4_S1_M01_phase2_feature_intake_validator"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_manifest(errors: list[str]) -> None:
    manifest = ROOT / "MANIFEST.csv"
    if not manifest.exists():
        errors.append("MANIFEST.csv is missing")
        return
    with manifest.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    declared = {row["path"]: row for row in rows}
    actual = {
        path.relative_to(ROOT).as_posix(): path
        for path in ROOT.rglob("*")
        if path.is_file()
        and path.name not in {"MANIFEST.csv", "MANIFESTO.csv"}
        and path.suffix not in EXCLUDED_SUFFIXES
        and not any(part in EXCLUDED_PARTS for part in path.relative_to(ROOT).parts)
    }
    missing = sorted(set(declared) - set(actual))
    unlisted = sorted(set(actual) - set(declared))
    if missing:
        errors.append(f"manifest references missing files: {missing[:10]}")
    if unlisted:
        errors.append(f"manifest omits files: {unlisted[:10]}")
    for relative, path in actual.items():
        row = declared.get(relative)
        if row is None:
            continue
        if int(row["size_bytes"]) != path.stat().st_size:
            errors.append(f"size mismatch: {relative}")
        if row["sha256"] != _sha256(path):
            errors.append(f"hash mismatch: {relative}")


def _check_yaml(errors: list[str]) -> None:
    for folder in (ROOT / "contracts", ROOT / "schemas", ROOT / "registries"):
        for path in folder.rglob("*.yaml"):
            try:
                yaml.safe_load(path.read_text(encoding="utf-8"))
            except Exception as exc:  # validation tool: preserve exact parser failure
                errors.append(f"invalid YAML {path.relative_to(ROOT)}: {exc}")


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
        return f"{node.func.value.id}.{node.func.attr}"
    return None


def _check_python(errors: list[str]) -> None:
    forbidden_calls = {
        "eval",
        "exec",
        "compile",
        "os.system",
        "subprocess.run",
        "subprocess.Popen",
    }
    for path in PHASE.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        lines = text.count("\n") + 1
        if lines > HARD_FILE_LINES:
            errors.append(f"file exceeds {HARD_FILE_LINES} lines: {path.relative_to(ROOT)} ({lines})")
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            errors.append(f"syntax error {path.relative_to(ROOT)}: {exc}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                size = int(node.end_lineno or node.lineno) - node.lineno + 1
                if size > HARD_FUNCTION_LINES:
                    errors.append(
                        f"function exceeds {HARD_FUNCTION_LINES} lines: "
                        f"{path.relative_to(ROOT)}:{node.lineno} {node.name} ({size})"
                    )
            elif isinstance(node, ast.ClassDef):
                size = int(node.end_lineno or node.lineno) - node.lineno + 1
                if size > HARD_CLASS_LINES:
                    errors.append(
                        f"class exceeds {HARD_CLASS_LINES} lines: "
                        f"{path.relative_to(ROOT)}:{node.lineno} {node.name} ({size})"
                    )
            elif isinstance(node, ast.Call):
                name = _call_name(node)
                if name in forbidden_calls:
                    errors.append(f"dynamic execution in productive source: {path.relative_to(ROOT)}:{node.lineno} {name}")


def _check_wrappers(errors: list[str]) -> None:
    wrappers = sorted(
        path for path in (PHASE / "modules").glob("P4_S*_M*.py")
        if path.stem not in LEGACY_COMPATIBILITY_ALIASES
    )
    if len(wrappers) != 49:
        errors.append(f"expected 49 module wrappers, found {len(wrappers)}")
    for path in wrappers:
        text = path.read_text(encoding="utf-8")
        lines = text.count("\n") + 1
        if lines > HARD_WRAPPER_FILE_LINES:
            errors.append(f"wrapper exceeds {HARD_WRAPPER_FILE_LINES} lines: {path.name} ({lines})")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                size = int(node.end_lineno or node.lineno) - node.lineno + 1
                if size > HARD_WRAPPER_FUNCTION_LINES:
                    errors.append(
                        f"wrapper function exceeds {HARD_WRAPPER_FUNCTION_LINES} lines: "
                        f"{path.name}:{node.lineno} {node.name} ({size})"
                    )


def _check_clean_tree(errors: list[str]) -> None:
    forbidden_names = {"__pycache__", ".pytest_cache", ".coverage", "build", "dist"}
    for path in ROOT.rglob("*"):
        if path.name in forbidden_names or path.suffix == ".pyc":
            errors.append(f"generated/cache artifact present: {path.relative_to(ROOT)}")


def _check_contracts(errors: list[str]) -> None:
    catalog_path = ROOT / "MODULE_CATALOG.csv"
    with catalog_path.open(newline="", encoding="utf-8") as handle:
        catalog = list(csv.DictReader(handle))
    expected_ids = {row["module_id"] for row in catalog}
    canonical_dir = ROOT / "contracts" / "modules"
    contracts = sorted(canonical_dir.glob("P4_*.yaml"))
    if len(contracts) != 49:
        errors.append(f"expected 49 canonical module contracts, found {len(contracts)}")
    contract_ids: set[str] = set()
    for path in contracts:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        module_id = str(data.get("module_id") or "")
        if not module_id:
            errors.append(f"module contract lacks module_id: {path.relative_to(ROOT)}")
            continue
        contract_ids.add(module_id)
        if data.get("contract_version") != "p4.v14.9-rc1.module.v1":
            errors.append(f"stale contract version: {path.relative_to(ROOT)}")
    if contract_ids != expected_ids:
        errors.append(
            "canonical contract IDs differ from module catalog: "
            f"missing={sorted(expected_ids-contract_ids)[:10]} extra={sorted(contract_ids-expected_ids)[:10]}"
        )

    matrix_path = ROOT / "contracts" / "MODULE_IO_MATRIX.yaml"
    matrix = yaml.safe_load(matrix_path.read_text(encoding="utf-8")) or {}
    entries = matrix.get("module_io_matrix", [])
    if len(entries) != 49:
        errors.append(f"combined module matrix must have 49 entries, found {len(entries)}")
    for entry in entries:
        relative = str(entry.get("module_contract") or "")
        target = ROOT / relative
        if not relative or not target.is_file():
            errors.append(f"matrix references missing module contract: {relative}")

    for matrix_file in (ROOT / "contracts").glob("*/MODULE_IO_MATRIX.yaml"):
        data = yaml.safe_load(matrix_file.read_text(encoding="utf-8")) or {}
        for entry in data.get("module_io_matrix", []):
            relative = str(entry.get("module_contract") or "")
            if not relative or not (ROOT / relative).is_file():
                errors.append(
                    f"{matrix_file.relative_to(ROOT)} references missing contract: {relative}"
                )

    s4_schemas = sorted((ROOT / "schemas" / "s4").glob("*.schema.yaml"))
    if len(s4_schemas) != 8:
        errors.append(f"expected 8 active S4 schemas, found {len(s4_schemas)}")
    s4_outputs = yaml.safe_load(
        (ROOT / "contracts" / "s4" / "OUTPUT_CONTRACTS.yaml").read_text(encoding="utf-8")
    )
    for name, spec in s4_outputs.get("outputs", {}).items():
        schema_path = ROOT / str(spec.get("schema") or "")
        if not schema_path.is_file():
            errors.append(f"S4 output {name} references missing schema {schema_path.relative_to(ROOT)}")


def _check_contract_authority(errors: list[str]) -> None:
    authority_path = ROOT / "contracts" / "CONTRACT_AUTHORITY.yaml"
    if not authority_path.is_file():
        errors.append("contract authority declaration is missing")
        return
    authority = yaml.safe_load(authority_path.read_text(encoding="utf-8")) or {}
    canonical_root = ROOT / str(authority.get("canonical_root") or "")
    mirror_roots = [
        ROOT / str(item.get("path") if isinstance(item, dict) else item)
        for item in authority.get("mirror_roots", [])
    ]
    canonical = {path.name: path for path in canonical_root.glob("P4_*.yaml")}
    if len(canonical) != 49:
        errors.append(f"contract authority canonical count must be 49, found {len(canonical)}")
    for mirror_root in mirror_roots:
        mirror = {path.name: path for path in mirror_root.glob("P4_*.yaml")}
        if not set(mirror).issubset(set(canonical)):
            errors.append(
                f"contract mirror contains non-canonical IDs: {mirror_root.relative_to(ROOT)}"
            )
            continue
        for name, mirror_path in mirror.items():
            canonical_path = canonical[name]
            if _sha256(canonical_path) != _sha256(mirror_path):
                errors.append(f"contract mirror hash mismatch: {mirror_root.relative_to(ROOT)}/{name}")

    aliases = authority.get("compatibility_aliases", [])
    if not isinstance(aliases, list):
        errors.append("contract authority compatibility_aliases must be a list")
        return
    alias_stems = {str(item.get("alias_stem") or "") for item in aliases if isinstance(item, dict)}
    if alias_stems != LEGACY_COMPATIBILITY_ALIASES:
        errors.append(
            "compatibility aliases differ from the declared legacy surface: "
            f"expected={sorted(LEGACY_COMPATIBILITY_ALIASES)} found={sorted(alias_stems)}"
        )
    with (ROOT / "MODULE_CATALOG.csv").open(newline="", encoding="utf-8") as handle:
        catalog_ids = {str(row["module_id"]) for row in csv.DictReader(handle)}
    for item in aliases:
        if not isinstance(item, dict):
            errors.append("compatibility alias entry must be an object")
            continue
        required = (
            "source_path",
            "canonical_source_path",
            "canonical_filename",
            "generated_at",
            "generated_by",
            "requirements_covered",
            "validation_result",
        )
        missing = [key for key in required if not item.get(key)]
        if missing:
            errors.append(f"compatibility alias {item.get('alias_stem')} missing provenance: {missing}")
            continue
        alias_path = ROOT / str(item["source_path"])
        canonical_path = ROOT / str(item["canonical_source_path"])
        if not alias_path.is_file():
            errors.append(f"compatibility alias source is missing: {item['source_path']}")
        if not canonical_path.is_file():
            errors.append(f"compatibility alias canonical source is missing: {item['canonical_source_path']}")
        if str(item.get("module_id")) not in catalog_ids:
            errors.append(f"compatibility alias points to non-canonical module: {item.get('module_id')}")
        if str(item.get("alias_stem")) in catalog_ids:
            errors.append(f"compatibility alias is incorrectly present in MODULE_CATALOG: {item['alias_stem']}")


def main() -> int:
    errors: list[str] = []
    _check_yaml(errors)
    _check_contracts(errors)
    _check_contract_authority(errors)
    _check_python(errors)
    _check_wrappers(errors)
    _check_clean_tree(errors)
    _check_manifest(errors)
    if errors:
        print("RELEASE VALIDATION: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("RELEASE VALIDATION: PASS")
    print("modules=49")
    print("subphases=9")
    print("manifest=verified")
    print("yaml=valid")
    print("productive_python=static_safe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
