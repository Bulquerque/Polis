"""Access installed S4 schemas and registries through importlib.resources."""

from __future__ import annotations

from importlib.resources import files


def read_schema(name: str) -> str:
    return (
        files("quant_pipeline.phase_09.subphases.s04_performance_risk.resources")
        .joinpath("schemas", name)
        .read_text(encoding="utf-8")
    )


def read_registry(name: str) -> str:
    return (
        files("quant_pipeline.phase_09.subphases.s04_performance_risk.resources")
        .joinpath("registries", name)
        .read_text(encoding="utf-8")
    )
