"""Explicit handler registry; no reflection or import-time magic."""
from __future__ import annotations

from .builder import FixedPopulationBuilder
from .validator import PopulationConsistencyValidator

MODULE_HANDLERS = {
    "P3.S7.M01": FixedPopulationBuilder().execute,
    "P3.S7.M02": PopulationConsistencyValidator().execute,
}
