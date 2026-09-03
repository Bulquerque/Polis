# Polis

Polis is a modular quantitative research pipeline for daily point-in-time analysis and reproducible backtesting.

The pipeline is composed of independently installable phase packages:

`ingestion → point-in-time quality → RAG and memory → features → forecasts → candidates → ranking → portfolio and backtest → robustness and learning`

## Capabilities

- provider-aware ingestion with lineage and content hashing;
- temporal validity rules that keep `valid_time` and `knowledge_time` separate;
- governed context, retrieval and memory boundaries;
- feature construction designed to prevent look-ahead leakage;
- forecast, candidate-generation and deterministic-ranking components;
- portfolio sizing, risk controls, transaction-cost modelling and backtest ledgers;
- typed contracts, schemas, package-level tests and reproducible command-line entry points.

## Repository layout

| Area | Location |
| --- | --- |
| Phase packages | `packages/` |
| Shared contracts | `contracts/global/` and each package's `contracts/` |
| Schemas and resources | Inside the relevant package under `schemas/`, `configs/`, `references/` or `resources/` |
| Package tests | Each package's `tests/` directory |
| Runtime configuration template | `.env.example` |
| Architecture and execution guide | `docs/` |

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the end-to-end flow and [docs/PACKAGE_GUIDE.md](docs/PACKAGE_GUIDE.md) for package-specific entry points.

## Start here

1. Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the data and decision flow.
2. Inspect `packages/p1-ingestion` for provider boundaries, lineage and credential handling.
3. Inspect `packages/p4-feature-base` for point-in-time features and fold construction.
4. Inspect `packages/p7_canonical_rc3` for deterministic ranking and handoff contracts.
5. Inspect `packages/p8_integrated_rc3` and `packages/p9_canonical_unified_rc4` for ledger, risk, robustness and learning surfaces.

The modular boundaries keep data contracts, implementation and tests close to one another.

## Quick start

Use Python 3.13 for the integrated packages. Create an isolated environment, install the package you want to inspect, and follow its local README:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

For a dependency-free structural smoke check:

```powershell
python -m compileall packages
```

Each package keeps its own build metadata and local test suite; [docs/PACKAGE_GUIDE.md](docs/PACKAGE_GUIDE.md) maps the entry points.

Provider credentials belong in the operator environment. Never commit `.env` files, private keys or access tokens; `.env.example` contains names only.

## Engineering boundaries

This is a research and backtesting codebase. It is intentionally separated from live trading, production promotion and financial execution. External provider access and paid datasets are configured at runtime and are not bundled with the repository.

Runtime qualification runs, generated reports, raw datasets, caches and machine-specific outputs are not stored in this repository. The source packages, contracts, schemas and tests are kept versioned.

Run a package-level test suite with the provider credentials and data entitlement appropriate to that package. Private credentials and paid datasets are never embedded in source control.

## License

No redistribution or commercial-use license is granted by this repository unless agreed separately by the owner.
