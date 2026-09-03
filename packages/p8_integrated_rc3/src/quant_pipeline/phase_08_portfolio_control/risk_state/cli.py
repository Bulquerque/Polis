"""CLI for strict JSON execution of P8.S4."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .api import run_s4
from .contracts import S4Request


def main() -> int:
    parser = argparse.ArgumentParser(description="Run P8.S4 risk-state construction")
    parser.add_argument("request_json", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    request = S4Request.model_validate_json(args.request_json.read_text(encoding="utf-8"))
    result = run_s4(request, args.output_dir)
    print(json.dumps(result.model_dump(mode="json"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
