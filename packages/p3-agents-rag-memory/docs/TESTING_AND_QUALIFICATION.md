# Testing and qualification

Required gates:

1. Compile/import all 81 module entrypoints.
2. Validate Contract Pack V2 schemas and registries.
3. Run unit and subphase integration suites.
4. Run the real foundation-to-runtime boundary tests.
5. Validate dry-run, warm-up, live and replay behavior.
6. Validate P2/P4/P9 schemas in the target repository.
7. Run Ruff, mypy and whole-source coverage in the target Python environment.

Passing internal tests does not by itself authorize production promotion.
