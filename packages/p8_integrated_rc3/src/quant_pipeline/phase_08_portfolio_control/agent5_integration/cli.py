from __future__ import annotations
import argparse
from pathlib import Path
from .models import Agent5IntegratedRequest
from .orchestrator import run_agent5_integrated

def main() -> int:
    parser=argparse.ArgumentParser(description="Run integrated P8 Agent 5 S9→S10 flow")
    parser.add_argument("input",type=Path); parser.add_argument("output",type=Path)
    args=parser.parse_args()
    request=Agent5IntegratedRequest.model_validate_json(args.input.read_text(encoding="utf-8"))
    result=run_agent5_integrated(request)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(result.model_dump_json(indent=2),encoding="utf-8")
    return 0
if __name__ == "__main__": raise SystemExit(main())
