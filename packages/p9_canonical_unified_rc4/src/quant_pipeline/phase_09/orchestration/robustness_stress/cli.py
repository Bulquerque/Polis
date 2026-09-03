from __future__ import annotations

import argparse
from pathlib import Path

from .contracts import RobustnessStressRunRequest
from .runner import run_robustness_stress


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run P9 S5-S6 S5→S6")
    parser.add_argument("request", type=Path, help="Combined RobustnessStressRunRequest JSON")
    parser.add_argument("output", type=Path, help="Destination JSON")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    request = RobustnessStressRunRequest.model_validate_json(args.request.read_text(encoding="utf-8"))
    output = run_robustness_stress(request)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(output.model_dump_json(indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
