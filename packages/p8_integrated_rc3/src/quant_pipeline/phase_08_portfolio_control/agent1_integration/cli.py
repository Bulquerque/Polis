"""Small operational CLI for the Agent 1 integration package."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .contracts import Agent1IntegrationReceiptV1
from .schema_export import export_schema


def main() -> int:
    parser = argparse.ArgumentParser(prog="p8-agent1")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("info")
    schemas = sub.add_parser("generate-schema")
    schemas.add_argument("target", type=Path)
    receipt = sub.add_parser("validate-receipt")
    receipt.add_argument("receipt", type=Path)
    args = parser.parse_args()
    if args.command == "info":
        sys.stdout.write(json.dumps({
            "package": "quant-pipeline-p8-agent1",
            "version": __version__,
            "components": {"S1": "0.1.0", "S2": "0.1.0"},
        }, indent=2) + "\n")
        return 0
    if args.command == "generate-schema":
        path = export_schema(args.target)
        sys.stdout.write(json.dumps({"written": str(path)}, indent=2) + "\n")
        return 0
    model = Agent1IntegrationReceiptV1.model_validate_json(args.receipt.read_bytes(), strict=True)
    sys.stdout.write(json.dumps({"status": "PASS", "content_sha256": model.content_sha256}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
