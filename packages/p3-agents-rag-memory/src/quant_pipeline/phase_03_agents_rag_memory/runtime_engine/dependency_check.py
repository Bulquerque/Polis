from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec


@dataclass(frozen=True, slots=True)
class DependencyCapability:
    name: str
    installed: bool
    required_for_core: bool
    purpose: str
    fallback: str


def dependency_capabilities() -> tuple[DependencyCapability, ...]:
    rows = (
        ("pydantic", True, "strict boundary contracts", "none"),
        ("httpx", False, "optional provider adapters", "offline/replay adapters"),
        ("yaml", True, "configuration parsing", "JSON configuration"),
        ("jsonschema", True, "P0/schema validation", "Pydantic validation"),
        ("pyarrow", False, "optional Parquet artifact IO", "JSON/SQLite artifact adapter"),
        ("mcp", False, "optional MCP tool transport", "local/HTTP ToolGatewayPort adapter"),
        ("hypothesis", False, "optional property tests", "deterministic pytest parametrization"),
        ("ruff", False, "optional quality gate", "uvx ruff in CI"),
        ("mypy", False, "optional static type gate", "uvx mypy in CI"),
    )
    return tuple(
        DependencyCapability(
            name=name,
            installed=find_spec(name) is not None,
            required_for_core=required,
            purpose=purpose,
            fallback=fallback,
        )
        for name, required, purpose, fallback in rows
    )


def missing_core_dependencies() -> tuple[str, ...]:
    return tuple(item.name for item in dependency_capabilities() if item.required_for_core and not item.installed)
