
"""Narrow ports used by S2."""

from typing import Protocol

from .debug import S2FailureDebugBundle


class DebugBundleWriterPort(Protocol):
    def write_failure(self, bundle: S2FailureDebugBundle) -> None: ...
