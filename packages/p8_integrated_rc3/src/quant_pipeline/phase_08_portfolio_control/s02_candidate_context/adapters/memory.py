
"""In-memory adapters for S2 testing and local execution."""

from dataclasses import dataclass, field

from ..debug import S2FailureDebugBundle


@dataclass(slots=True)
class InMemoryDebugBundleWriter:
    failures: list[S2FailureDebugBundle] = field(default_factory=list)

    def write_failure(self, bundle: S2FailureDebugBundle) -> None:
        self.failures.append(bundle)
