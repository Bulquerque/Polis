"""Small CLI for schema generation and P7 handoff validation."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from quant_pipeline.phase_08_contracts.enums import RuntimeMode

from .context import S1ExecutionContext
from .modules.m01_phase7_handoff_contract_validator import run_module
from .policies import ContractCompatibilityPolicy
from .schema_export import export_schemas


def _context_from_args(args: argparse.Namespace) -> S1ExecutionContext:
    return S1ExecutionContext(
        run_id=args.run_id,
        cycle_id=args.cycle_id,
        cycle_sequence=args.cycle_sequence,
        decision_time=datetime.fromisoformat(args.decision_time.replace("Z", "+00:00")),
        market_cutoff_at=datetime.fromisoformat(args.market_cutoff_at.replace("Z", "+00:00")),
        computed_at=datetime.fromisoformat(args.computed_at.replace("Z", "+00:00")),
        runtime_mode=RuntimeMode(args.runtime_mode),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="p8-s1")
    subparsers = parser.add_subparsers(dest="command", required=True)
    schemas = subparsers.add_parser("generate-schemas")
    schemas.add_argument("target", type=Path)
    validate = subparsers.add_parser("validate-handoff")
    validate.add_argument("handoff", type=Path)
    validate.add_argument("--run-id", required=True)
    validate.add_argument("--cycle-id", required=True)
    validate.add_argument("--cycle-sequence", required=True, type=int)
    validate.add_argument("--decision-time", required=True)
    validate.add_argument("--market-cutoff-at", required=True)
    validate.add_argument("--computed-at", required=True)
    validate.add_argument("--runtime-mode", choices=[mode.value for mode in RuntimeMode], default="BACKTEST")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.command == "generate-schemas":
        paths = export_schemas(args.target)
        sys.stdout.write(json.dumps({"written": [str(path) for path in paths]}, indent=2) + "\n")
        return 0
    context = _context_from_args(args)
    result = run_module(args.handoff.read_bytes(), context=context, policy=ContractCompatibilityPolicy())
    sys.stdout.write(result.model_dump_json(indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
