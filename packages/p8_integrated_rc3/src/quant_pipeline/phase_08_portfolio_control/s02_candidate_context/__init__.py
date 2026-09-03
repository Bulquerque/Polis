
"""P8.S2 public package surface."""

from .api import S2RunRequest, S2RunResult, build_s2_input_bundle, run_s2
from .contracts.bundle import P8CandidateContextBundleV1, S2InputBundleV1

__all__ = [
    "P8CandidateContextBundleV1",
    "S2InputBundleV1",
    "S2RunRequest",
    "S2RunResult",
    "build_s2_input_bundle",
    "run_s2",
]
