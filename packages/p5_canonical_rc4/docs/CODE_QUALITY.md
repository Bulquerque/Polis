# Code quality

- Maximum 350 lines per source file, 60 per function and 180 per class.
- Strong typing is configured through mypy strict; execution is pending where mypy is unavailable.
- Ruff, Hypothesis and the Python 3.11–3.14 matrix remain configured external gates.
- No hidden economic defaults, input mutation, network dependency in tests or parallel P5 engine.
- Bounded CPU-first algorithms and deterministic seeds are required.
