"""Command-line interface for the integrated P3 package."""
from __future__ import annotations

import argparse
import asyncio
import importlib
import importlib.metadata
import json
import sys
from dataclasses import asdict
from pathlib import Path

import yaml

from ..final_integration.models import PublicKeyRecord
from .registry import EXECUTABLE_MODULE_REGISTRY
from .release_validation import (
    validate_documentation_links,
    validate_final_integration_contracts,
    validate_global_authority_patch,
    validate_global_schema_versions,
    validate_schema_registry_hashes,
    validate_release_identity,
)
from .validator import validate_registry, validate_source_tree

OPTIONAL_PACKAGES = {
    "api": "httpx",
    "mcp": "mcp",
    "parquet": "pyarrow",
    "neo4j": "neo4j",
    "observability": "opentelemetry-api",
}


def _find_project_root() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return None


def _load_keyring(path: Path) -> dict[str, PublicKeyRecord]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_keys = payload.get("keys", payload) if isinstance(payload, dict) else None
    if not isinstance(raw_keys, dict) or not raw_keys:
        raise ValueError("keyring must contain a non-empty keys mapping")
    return {
        str(key_id): PublicKeyRecord.model_validate(record)
        for key_id, record in raw_keys.items()
    }


def _release_identity(root: Path, args: argparse.Namespace) -> tuple[str, str]:
    path = root / "RELEASE.json"
    payload = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    release_id = getattr(args, "release_id", None) or payload.get("release_id")
    release_sha256 = getattr(args, "release_sha256", None) or payload.get(
        "content_sha256"
    )
    if not isinstance(release_id, str) or not isinstance(release_sha256, str):
        raise ValueError("release identity is missing; provide arguments or RELEASE.json")
    return release_id, release_sha256


def dependency_report() -> dict[str, object]:
    report: dict[str, object] = {"python": sys.version.split()[0], "core": {}, "optional": {}}
    for package in ("pydantic", "PyYAML", "jsonschema", "cryptography"):
        try:
            report["core"][package] = importlib.metadata.version(package)  # type: ignore[index]
        except importlib.metadata.PackageNotFoundError:
            report["core"][package] = None  # type: ignore[index]
    for extra, package in OPTIONAL_PACKAGES.items():
        try:
            value = {
                "package": package,
                "installed": True,
                "version": importlib.metadata.version(package),
            }
        except importlib.metadata.PackageNotFoundError:
            value = {"package": package, "installed": False, "version": None}
        report["optional"][extra] = value  # type: ignore[index]
    return report


def validate_release(root: Path, *, strict_hygiene: bool = False) -> list[str]:
    errors = (
        validate_registry()
        + validate_source_tree(root / "src")
        + validate_schema_registry_hashes(root)
        + validate_documentation_links(root)
        + validate_global_authority_patch(root)
        + validate_global_schema_versions(root)
        + validate_final_integration_contracts(root)
        + validate_release_identity(root)
    )
    if len(EXECUTABLE_MODULE_REGISTRY) != 128:
        errors.append(f"executable module registry has {len(EXECUTABLE_MODULE_REGISTRY)} entries; expected 128")
    for registration in EXECUTABLE_MODULE_REGISTRY:
        try:
            importlib.import_module(registration.implementation_path)
        except Exception as exc:
            errors.append(f"{registration.module_id} import failed: {exc}")
    for relative in (
        "contracts/P3_INTEGRATION_CONTRACT_PACK_V2.yaml",
        "contracts/MODULE_REGISTRY.yaml",
        "schemas/SCHEMA_REGISTRY.yaml",
        "contracts/FINAL_INTEGRATION_ARTIFACT_SCHEMA_BINDINGS.yaml",
    ):
        path = root / relative
        if not path.is_file():
            errors.append(f"missing {relative}")
            continue
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                errors.append(f"{relative} must contain a mapping")
        except Exception as exc:
            errors.append(f"invalid {relative}: {exc}")
    if strict_hygiene:
        # Keep validation aligned with ``tools/release.py``. Test execution
        # necessarily creates caches inside the working tree; those paths are
        # excluded from the immutable package and must not make a valid source
        # tree un-releasable. Root-level operational artifacts still remain
        # visible to the checks below.
        transient_dirs = {
            ".git",
            ".venv",
            ".venv-p3",
            "venv",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            ".hypothesis",
            "htmlcov",
            "build",
            "dist",
        }
        transient_names = {".coverage"}
        for path in root.rglob("*"):
            relative = path.relative_to(root)
            if any(part in transient_dirs or part.endswith(".egg-info") for part in relative.parts):
                continue
            if path.name in transient_names or path.suffix in {".pyc", ".pyo", ".zip", ".whl"}:
                errors.append(f"transient release artifact present: {path.relative_to(root)}")
    return errors


def _print(payload: dict[str, object]) -> int:
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    return 0 if str(payload.get("status", "")).startswith("PASS") else 1


def _add_release_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--release-id")
    parser.add_argument("--release-sha256")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="p3")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="report dependency availability")
    subparsers.add_parser("modules", help="print the 128 executable module bindings")

    validate = subparsers.add_parser(
        "validate", help="validate imports, registries, contracts and release files"
    )
    validate.add_argument("--strict-hygiene", action="store_true")

    real = subparsers.add_parser(
        "run-pipeline-real",
        help="run an environment-supplied production S1-S31 driver",
    )
    real.add_argument("--driver", required=True, help="module:factory")
    real.add_argument("--config", type=Path, required=True)
    real.add_argument("--output-dir", type=Path, required=True)
    real.add_argument("--keyring", type=Path, required=True)
    _add_release_args(real)

    initialize = subparsers.add_parser(
        "integration-init", help="create fail-closed integration evidence templates"
    )
    initialize.add_argument("--output-dir", type=Path, required=True)

    run = subparsers.add_parser(
        "integration-run",
        help="run an environment-supplied integration evidence driver",
    )
    run.add_argument("--driver", required=True, help="module:factory")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--output-dir", type=Path, required=True)

    tools_run = subparsers.add_parser(
        "research-tools-run",
        help="execute one complete research-tools batch and write one receipt",
    )
    tools_run.add_argument("--driver", required=True, help="module:factory with prepare(config, output_dir)")
    tools_run.add_argument("--config", type=Path, required=True)
    tools_run.add_argument("--output", type=Path, required=True)

    qualify = subparsers.add_parser(
        "integration-qualify", help="evaluate the signed integration evidence chain"
    )
    qualify.add_argument("--evidence-dir", type=Path, required=True)
    qualify.add_argument("--keyring", type=Path, required=True)
    qualify.add_argument("--output", type=Path)
    _add_release_args(qualify)

    candidate = subparsers.add_parser(
        "integration-build-candidate",
        help="build an immutable P0 promotion candidate after all prior gates pass",
    )
    candidate.add_argument("--evidence-dir", type=Path, required=True)
    candidate.add_argument("--keyring", type=Path, required=True)
    candidate.add_argument("--output", type=Path, required=True)
    _add_release_args(candidate)

    args = parser.parse_args(argv)
    root = _find_project_root()
    if args.command == "doctor":
        return _print(
            {
                "status": "PASS",
                "contract_pack": "P3_INTEGRATION_CONTRACT_PACK_V2",
                "dependencies": dependency_report(),
            }
        )
    if args.command == "modules":
        return _print(
            {
                "status": "PASS",
                "module_count": len(EXECUTABLE_MODULE_REGISTRY),
                "modules": [asdict(item) for item in EXECUTABLE_MODULE_REGISTRY],
            }
        )
    if root is None:
        return _print({"status": "FAIL", "errors": ["project root not found"]})
    if args.command == "validate":
        errors = validate_release(root, strict_hygiene=args.strict_hygiene)
        return _print(
            {
                "status": "PASS" if not errors else "FAIL",
                "errors": errors,
                "module_count": len(EXECUTABLE_MODULE_REGISTRY),
                "dependencies": dependency_report(),
            }
        )
    if args.command == "integration-init":
        from ..final_integration.templates import write_templates

        paths = write_templates(args.output_dir)
        return _print(
            {
                "status": "PASS",
                "template_count": len(paths),
                "output_dir": str(args.output_dir.resolve()),
                "qualification_status": "FAIL_NOT_QUALIFIED",
            }
        )
    if args.command == "integration-run":
        from ..final_integration.driver import run_driver

        try:
            payload = run_driver(args.driver, args.config, args.output_dir)
        except Exception as exc:
            return _print({"status": "FAIL", "errors": [str(exc)]})
        return _print(
            {
                "status": "PASS",
                "driver_result": payload,
                "output_dir": str(args.output_dir.resolve()),
            }
        )
    if args.command == "research-tools-run":
        from ..extensions.research_tools.runtime.unified_runner import run_unified_driver

        try:
            result = run_unified_driver(args.driver, args.config, args.output)
        except Exception as exc:
            return _print({"status": "FAIL", "errors": [str(exc)]})
        return _print(result)
    if args.command == "run-pipeline-real":
        from .real_pipeline import run_real_pipeline

        try:
            release_id, release_sha256 = _release_identity(root, args)
            result = asyncio.run(
                run_real_pipeline(
                    driver_ref=args.driver,
                    config_path=args.config,
                    keyring=_load_keyring(args.keyring),
                    release_id=release_id,
                    release_sha256=release_sha256,
                    output_dir=args.output_dir,
                )
            )
            return _print(result)
        except Exception as exc:
            return _print({"status": "FAIL_NOT_QUALIFIED", "errors": [str(exc)]})
    if args.command in {"integration-qualify", "integration-build-candidate"}:
        from ..final_integration.gates import FinalIntegrationGateEngine

        try:
            release_id, release_sha256 = _release_identity(root, args)
            engine = FinalIntegrationGateEngine(
                release_id=release_id,
                release_sha256=release_sha256,
                keyring=_load_keyring(args.keyring),
            )
            report = engine.evaluate(args.evidence_dir)
            if args.command == "integration-build-candidate":
                value = engine.build_candidate(args.evidence_dir, report)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(
                    json.dumps(
                        value.model_dump(mode="json"),
                        indent=2,
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                return _print(
                    {
                        "status": "PASS",
                        "candidate_path": str(args.output.resolve()),
                        "candidate_hash": value.bundle_hash,
                        "gate_report": report.model_dump(mode="json"),
                    }
                )
            payload = report.model_dump(mode="json")
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(
                    json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
                    + "\n",
                    encoding="utf-8",
                )
                payload["output_path"] = str(args.output.resolve())
            return _print(payload)
        except Exception as exc:
            return _print({"status": "FAIL", "errors": [str(exc)]})
    return _print({"status": "FAIL", "errors": ["unknown command"]})


if __name__ == "__main__":
    raise SystemExit(main())
