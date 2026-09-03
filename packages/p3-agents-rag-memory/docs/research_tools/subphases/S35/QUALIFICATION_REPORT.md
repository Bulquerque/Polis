# Relatório de qualificação local

## Status

```text
IMPLEMENTED_QUALIFIED_LOCAL
production_promotion_allowed = false
production_authority = P0_ONLY
```

## Evidência executada

- 28 testes próprios: todos passaram;
- 4 testes da P3.S12 original: todos passaram;
- 14 testes da P3.S20 original: todos passaram;
- 9 testes da P3.S21 original: todos passaram;
- 7 testes de smoke em merge real sobre cópia da P3: todos passaram;
- build de wheel: passou;
- instalação do wheel e import conjunto com a P3 base: passou;
- cobertura com branches: 85%;
- nenhum timeout ou processo preso.

Os grupos foram executados sequencialmente, sem `xdist`, multiprocessing ou fork.

## Qualificação por capacidade

- BM25 lexical, point-in-time, hashes e snapshot: qualificados localmente;
- RRF: qualificado quando existe mais de um ranking;
- dense retrieval: porta opcional, não qualificada sem provider snapshot-pinned;
- reranker: porta opcional, não qualificada sem provider snapshot-pinned;
- `FORENSIC`: bloqueado quando o grafo de versões não está disponível;
- proveniência até P1: degradada quando o boundary não fornece a referência completa;
- promoção produtiva: permanece bloqueada até integração S40 e decisão P0.
