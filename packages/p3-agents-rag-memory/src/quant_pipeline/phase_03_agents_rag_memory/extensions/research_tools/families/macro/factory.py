from __future__ import annotations

from .catalog_contracts import AssetMacroContextRegistrySnapshot, MacroSeriesReleaseCatalog
from .handlers import MacroHandlers, MacroRuntimeHandlerBundle
from .ports import PitMacroQueryPort


def create_macro_runtime_bundle(
    boundary: PitMacroQueryPort,
    catalog: MacroSeriesReleaseCatalog,
    context_registry: AssetMacroContextRegistrySnapshot,
) -> MacroRuntimeHandlerBundle:
    return MacroHandlers(boundary, catalog, context_registry).bundle()
