from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from .models_evidence import RuntimeAssuranceRequest
from .orchestrator import run_runtime_assurance
from .schema_export import export_schemas


def _load_request(path: Path) -> RuntimeAssuranceRequest:
    return RuntimeAssuranceRequest.model_validate_json(path.read_text(encoding="utf-8"))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="p8-s9")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-request")
    validate.add_argument("request", type=Path)
    run = sub.add_parser("run")
    run.add_argument("request", type=Path)
    run.add_argument("--output", type=Path)
    export = sub.add_parser("export-schemas")
    export.add_argument("output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "export-schemas":
            paths = export_schemas(args.output)
            print(json.dumps({"schemas": [str(path) for path in paths]}, indent=2))
            return 0
        request = _load_request(args.request)
        if args.command == "validate-request":
            print(json.dumps({"valid": True, "run_id": request.context.run_id}))
            return 0
        result = run_runtime_assurance(request)
        text = result.model_dump_json(indent=2)
        if args.output is None:
            print(text)
        else:
            args.output.write_text(text + "\n", encoding="utf-8")
        return 0
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
