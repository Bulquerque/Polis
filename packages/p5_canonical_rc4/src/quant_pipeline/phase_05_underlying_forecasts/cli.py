"""Portable command-line diagnostics for the P5 package."""
from __future__ import annotations

import argparse
import json
from importlib.metadata import PackageNotFoundError, version

from .registry import list_modules


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="p5")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="validate import and module registry")
    subparsers.add_parser("list-modules", help="list canonical module IDs")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    modules = list_modules()
    if args.command == "doctor":
        try:
            package_version = version("quant-pipeline-p5-canonical")
        except PackageNotFoundError:
            package_version = "source-checkout"
        print(json.dumps({
            "status": "PASS",
            "package_version": package_version,
            "module_count": len(modules),
            "subphase_count": len({module.subphase_id for module in modules}),
        }, sort_keys=True))
        return 0
    for module in modules:
        print(f"{module.module_id}\t{module.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
