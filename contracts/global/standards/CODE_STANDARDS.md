# Canonical Code Standards — V14.1 RC4.1

## Fonte única

Este documento substitui padrões de código duplicados em fases individuais.

## Estilo

- Código pequeno, explícito e fail-fast.
- Inputs e outputs sempre explícitos.
- Sem estado global mutável.
- Sem conexão implícita entre fases.
- Sem arquivo monolítico.
- Sem helpers genéricos sem dono.
- Reutilizar `quant_pipeline.common` para contratos, hashing, schemas, manifests, logging e validação.

## Search-first

Antes de criar qualquer coisa, procurar no pacote e no source of truth.

## Estrutura

- `quant_pipeline.common`: utilitários transversais.
- `quant_pipeline.phase_xx_*`: lógica específica da fase.
- `contracts/`: contratos YAML.
- `schemas/`: schemas YAML.
- `tests/phase_specific`: testes locais da fase.
- Testes globais ficam na Fase 0.
