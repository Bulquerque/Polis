
"""CLI for deterministic execution of P8.S2 from a sealed S2 input bundle."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .api import S2RunRequest, run_s2
from .context import S2ExecutionContext
from .contracts.bundle import S2InputBundleV1


def main() -> int:
    parser = argparse.ArgumentParser(prog="p8-s2")
    parser.add_argument("input_bundle", type=Path)
    parser.add_argument("output_bundle", type=Path)
    parser.add_argument("--computed-at", required=True)
    args = parser.parse_args()
    bundle = S2InputBundleV1.model_validate_json(args.input_bundle.read_bytes(), strict=True)
    context = S2ExecutionContext(
        run_id=bundle.snapshot.run_id,
        cycle_id=bundle.snapshot.cycle_id,
        decision_time=bundle.snapshot.decision_time,
        computed_at=datetime.fromisoformat(args.computed_at.replace("Z", "+00:00")),
    )
    result = run_s2(S2RunRequest(input_bundle=bundle, context=context))
    args.output_bundle.parent.mkdir(parents=True, exist_ok=True)
    args.output_bundle.write_text(result.bundle.model_dump_json(indent=2) + "\n", encoding="utf-8")
    sys.stdout.write(json.dumps({
        "status": "PASS",
        "snapshot_id": result.bundle.snapshot_id,
        "forwarded_candidate_count": len(result.bundle.static_action_universe.forwarded_candidate_ids),
        "content_sha256": result.bundle.content_sha256,
    }, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
