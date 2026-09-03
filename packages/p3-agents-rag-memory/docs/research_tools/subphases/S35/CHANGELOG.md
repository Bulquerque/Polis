# Changelog

## 1.0.0 — 2026-08-04

- Implementados os cinco módulos canônicos de `P3.S35`.
- Reutilizado o índice congelado de S12, sem duplicar o RAG.
- Implementado BM25 local, RRF opcional, deduplicação e filtro PIT anterior ao ranking.
- Implementadas as seis operações de `research.corpus.v1`.
- Implementados contratos estritos, qualificação por operação/modo e ponte JSON compatível com S21.
- Tornado explícito o fallback de conteúdo bruto para conteúdo reconstruído.
- Namespaced o grafo de proveniência para evitar colisão de IDs entre P1, P2, fonte e chunk.
- Adicionados contratos, schemas, fixtures, documentação, validação e testes com timeout.
