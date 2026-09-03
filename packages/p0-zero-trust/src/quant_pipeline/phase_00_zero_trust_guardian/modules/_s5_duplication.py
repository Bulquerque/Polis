from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Callable
import fnmatch

COMMON_UTILITY_NAMES = frozenset({
    "contracts.py", "validators.py", "_module_executor.py", "hashing.py",
    "manifest.py", "logging.py", "schema_validation.py",
})


def _matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _authorized_pattern(paths: list[str], patterns: list[str]) -> bool:
    return bool(patterns) and all(_matches_any(path, patterns) for path in paths)


def _package_marker(paths: list[str]) -> bool:
    return {PurePosixPath(path).name for path in paths} == {"__init__.py"}


def _test_fixture(paths: list[str]) -> bool:
    return all("/fixtures/" in f"/{path}" or "/test" in f"/{path}" for path in paths)


def _schema_mirror(paths: list[str]) -> bool:
    return all(path.endswith(".schema.yaml") for path in paths)


def _common_utility(paths: list[str]) -> bool:
    return bool({PurePosixPath(path).name for path in paths} & COMMON_UTILITY_NAMES)


def _source_mirror(paths: list[str]) -> bool:
    return all("source_of_truth" in path for path in paths)


def classify_duplicate(paths: list[str], config: dict[str, Any]) -> tuple[str, bool]:
    patterns = config.get("allowlisted_duplicate_patterns", [])
    if patterns and not all(isinstance(item, str) and item for item in patterns):
        raise ValueError("allowlisted_duplicate_patterns must contain glob strings")
    rules: list[tuple[str, bool, Callable[[list[str]], bool]]] = [
        ("PACKAGE_MARKER", False, _package_marker),
        ("TEST_FIXTURE", False, _test_fixture),
        ("SCHEMA_MIRROR", False, _schema_mirror),
        ("DUPLICATED_COMMON_UTILITY", True, _common_utility),
        ("SOURCE_OF_TRUTH_MIRROR", False, _source_mirror),
    ]
    if _authorized_pattern(paths, patterns):
        return "AUTHORIZED_PATTERN", False
    for classification, blocking, predicate in rules:
        if predicate(paths):
            return classification, blocking
    return "EXACT_DUPLICATE", True
