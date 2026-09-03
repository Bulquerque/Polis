from __future__ import annotations

import argparse
from pathlib import Path

from .models import S6RunRequest
from .runner import run_s6
from .schema_export import export_schemas


def main() -> int:
    parser = argparse.ArgumentParser(description="Run or inspect P9.S6")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="Run S6 from a JSON request")
    run_parser.add_argument("request", type=Path)
    run_parser.add_argument("output", type=Path)
    schema_parser = subparsers.add_parser("schemas", help="Export JSON Schemas")
    schema_parser.add_argument("output_directory", type=Path)
    arguments = parser.parse_args()
    if arguments.command == "schemas":
        export_schemas(arguments.output_directory)
        return 0
    request = S6RunRequest.model_validate_json(arguments.request.read_text(encoding="utf-8"))
    result = run_s6(request)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(result.model_dump_json(indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
