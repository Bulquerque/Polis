# Migration V1→V2

`underlying_forecast_panel` remains a compact compatibility projection. Current P6 consumers should use the native `market_belief_state`; the V2 `Phase6StrategyScenarioManifest` remains the canonical P5 publication contract and is marked pending full P6 consumer support. Missing spot, option surface, skew, term structure or liquidity is represented as unavailable; no synthetic surface or price is generated.
