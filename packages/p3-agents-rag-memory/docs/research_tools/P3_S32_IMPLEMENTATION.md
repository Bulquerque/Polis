# P3.S32 Implementation

## Layout

- `extensions/research_tools/core`: modelos, IDs, hashing e falhas.
- `contracts`: contratos Pydantic e 34 pares request/result.
- `services`: quatro casos de uso S32.
- `s32.py`: fachada determinística.
- `modules/P3_S32_*`: wrappers canônicos finos.

## Regras de código

Modelos são estritos, congelados e `extra=forbid`. IDs e hashes são validados. Serialização canônica usa JSON ordenado, UTC e `allow_nan=False`. Não existe registro por side effect nem import dinâmico de handlers.

## Reprodutibilidade

`tools/research_tools/generate_s32_contracts.py` gera schemas. `build_s32_manifests.py` recalcula hashes e tamanhos. A execução M04 congela o snapshot.
