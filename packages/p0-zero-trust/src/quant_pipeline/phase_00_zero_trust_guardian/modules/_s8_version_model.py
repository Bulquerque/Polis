from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from ._module_executor import ContractValidationError

_VERSION_RE = re.compile(
    r"^V?(?P<major>\d+)\.(?P<minor>\d+)(?:-?RC(?P<rc>\d+)(?:\.(?P<revision>\d+))?)?$",
    re.IGNORECASE,
)


@dataclass(frozen=True, order=True)
class VersionInfo:
    major: int
    minor: int
    release_candidate: int = 0
    revision: int = 0

    @property
    def release_line(self) -> tuple[int, int]:
        return self.major, self.minor

    def as_dict(self) -> dict[str, int]:
        return {
            "major": self.major,
            "minor": self.minor,
            "release_candidate": self.release_candidate,
            "revision": self.revision,
        }


def parse_version(value: Any, *, label: str = "version") -> VersionInfo:
    text = str(value or "").strip()
    match = _VERSION_RE.fullmatch(text)
    if match is None:
        raise ContractValidationError(f"{label} is not a supported pipeline version: {text!r}")
    groups = match.groupdict(default="0")
    return VersionInfo(
        major=int(groups["major"]),
        minor=int(groups["minor"]),
        release_candidate=int(groups["rc"]),
        revision=int(groups["revision"]),
    )


def compare_versions(previous: VersionInfo, current: VersionInfo) -> tuple[str, bool]:
    if previous.release_line != current.release_line:
        return "INCOMPATIBLE_RELEASE_LINE", True
    if previous > current:
        return "VERSION_DOWNGRADE", True
    if previous == current:
        return "SAME_VERSION", False
    return "COMPATIBLE_FORWARD_REVISION", False
