# Fechamento transversal de qualidade P0→P4

## Objetivo

A nova P4 não copia cegamente nenhuma fase anterior. Ela combina a governança de P0, a simplicidade contratual de P1/P2 e os domínios tipados da P3, evitando os problemas concretos encontrados na auditoria estática.

## Evidência estática observada

| Fase | Python | LOC | Maior arquivo | Maior função | Diagnóstico principal |
|---|---:|---:|---:|---:|---|
| P0 | 99 | 14.066 | 400 | 115 | Autoridade forte, mas runner e alguns validadores já estão grandes. |
| P1 | 35 | 3.877 | 389 | 175 | Boa separação provider/transport; helpers semânticos e módulos de handoff concentram regras demais. |
| P2 | 34 | 5.282 | 546 | 149 | Boa consciência temporal; núcleos S1/S6 grandes e funções longas dificultam teste isolado. |
| P3 | 483 | 61.552 | 811 | 235 | Domínios, modelos e ports fortes; risco de fragmentação, arquivos gigantes, `common.py` e catches amplos. |
| P4 RC4.1 | 23 | 514 | 205 | 87 | Runner simples, mas wrappers finos demais e semântica econômica quase toda ausente. |

Os números são métricas estáticas do pacote P0–P9 auditado; não representam qualidade por si só, mas identificam extremos que a P4 deve evitar.

## Padrões absorvidos

### De P0
- contratos e schemas são a autoridade;
- produtor único por artefato;
- conexões allowlist;
- evidência e status sem overclaim;
- promoção final controlada externamente.

### De P1/P2
- runner pequeno e topológico;
- wrappers compatíveis e explícitos;
- fail-fast;
- separação entre adapters e domínio.

### De P3
- modelos imutáveis;
- `Protocol` para dependências externas;
- erros de domínio com códigos estáveis;
- replay determinístico;
- ports e adapters;
- recursos opcionais injetados.

## Problemas proibidos na P4

1. **God helpers:** nenhum `_semantic_helpers.py` central que conheça vários domínios.
2. **Wrappers fictícios:** wrapper fino não significa lógica ausente; ele deve chamar serviço real e testado.
3. **Mega-core:** nenhum `_s1_core.py` ou `quality.py` acumulando validação, transformação e I/O.
4. **Fragmentação excessiva:** não criar um arquivo para cada dataclass minúscula; agrupar por coesão de domínio.
5. **Arquivos enciclopédicos:** modelos e registries não podem crescer sem divisão por bounded context.
6. **`common.py`, `utils.py`, `helpers.py`:** nomes genéricos são bloqueados no core novo.
7. **Catch-all:** `except Exception` só na borda, traduzido para erro de domínio e preservando a causa.
8. **Defaults silenciosos:** tempo, lineage, entidade, valor e missingness nunca são inventados.
9. **DataFrame implícito:** grain, sort order, dtype e index precisam ser declarados no contrato.
10. **Imports entre agentes:** comunicação ocorre por artefatos e contratos, nunca importando implementação de outro agente.

## Arquitetura de referência

```text
contracts/models
  ↓
pure domain functions
  ↓
domain services
  ↓
adapters and ports
  ↓
thin module wrappers
  ↓
topological runner
```

Cada camada pode depender somente das camadas acima. A matemática reside em funções puras ou serviços de domínio; o wrapper não implementa fórmula, rede, filesystem ou política econômica.

## Gate de fechamento

A P4 só poderá ser chamada de implementada quando:
- os 49 módulos tiverem código real e testes;
- nenhum contrato for alterado fora do change-control;
- os três handoffs entre agentes passarem com fixtures e artefatos reais;
- os oito outputs legados forem consumidos pela P5;
- P0 registrar manifestos, hashes e evidências da mesma árvore.
