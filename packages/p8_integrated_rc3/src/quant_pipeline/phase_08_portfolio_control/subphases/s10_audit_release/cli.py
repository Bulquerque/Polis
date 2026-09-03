from __future__ import annotations
import argparse, json
from pathlib import Path
from pydantic import BaseModel
from .independent_auditor import run_independent_audit
from .models_orchestration import AuditReleaseRequest
from .models_release import ReleasePublicationRequest
from .models_state import StatefulEvidenceBundle
from .orchestrator import run_audit_release
from .release_publisher import publish_release
from .schema_export import export_schemas

def _load(model: type[BaseModel], path: str) -> BaseModel:
    return model.model_validate_json(Path(path).read_text(encoding="utf-8"))

def _write(model: BaseModel, output: str | None) -> None:
    text = model.model_dump_json(indent=2)
    if output:
        Path(output).write_text(text+"\n", encoding="utf-8")
    else:
        print(text)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="p8-s10")
    sub = parser.add_subparsers(dest="command", required=True)
    audit = sub.add_parser("audit"); audit.add_argument("input"); audit.add_argument("--output")
    run = sub.add_parser("run"); run.add_argument("input"); run.add_argument("--output")
    release = sub.add_parser("release"); release.add_argument("input"); release.add_argument("--output")
    schemas = sub.add_parser("export-schemas"); schemas.add_argument("output_dir")
    args = parser.parse_args(argv)
    if args.command == "audit":
        _write(run_independent_audit(_load(StatefulEvidenceBundle, args.input)), args.output); return 0
    if args.command == "run":
        _write(run_audit_release(_load(AuditReleaseRequest, args.input)), args.output); return 0
    if args.command == "release":
        _write(publish_release(_load(ReleasePublicationRequest, args.input)), args.output); return 0
    export_schemas(args.output_dir); return 0

if __name__ == "__main__":
    raise SystemExit(main())
