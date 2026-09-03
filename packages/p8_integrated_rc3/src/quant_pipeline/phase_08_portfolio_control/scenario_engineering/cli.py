"""Command-line entrypoint for deterministic file-based execution."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .api import run_s3
from .contracts import S3Request


def main() -> None:
    parser = argparse.ArgumentParser(description="Run P8.S3 scenario engineering")
    parser.add_argument("request", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    request = S3Request.model_validate_json(args.request.read_text(encoding="utf-8"))
    result = run_s3(request, output_dir=args.output)
    print(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
