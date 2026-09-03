from __future__ import annotations

from pathlib import Path

from quant_pipeline.phase_09.orchestration.robustness_stress import (
    RobustnessStressRunRequest,
    run_robustness_stress,
)


def main() -> None:
    directory = Path(__file__).resolve().parent
    request = RobustnessStressRunRequest.model_validate_json(
        (directory / "robustness_stress_request.json").read_text(encoding="utf-8")
    )
    output = run_robustness_stress(request)
    with (directory / "robustness_stress_output.json").open(
        "w", encoding="utf-8", newline="\n"
    ) as handle:
        handle.write(output.model_dump_json(indent=2) + "\n")


if __name__ == "__main__":
    main()
