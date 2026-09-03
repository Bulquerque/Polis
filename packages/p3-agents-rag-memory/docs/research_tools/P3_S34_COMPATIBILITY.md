# P3.S34 Compatibility Contract

## S15

S34 não altera S15. M04 lê o painel legado apenas para preservar denies e limites materiais. A extensão gera um painel novo no contrato do S21, com operações funcionais reais.

## S16

M04 aceita tanto a política S21 quanto a forma legada S16. A projeção preserva PIT, auditoria, timeout e limite de chamadas. MCP permanece transporte opcional; providers internos qualificados são usados por padrão.

## S20

O bundle S20 possui forma diferente do consumidor S21. M05 faz a camada anticorrupção:

```text
S20 context + budget report
→ seções preservadas
→ descriptors autorizados
→ S21 PersonContextRecord
```

Datas ISO são normalizadas para UTC. `text/content` e `source_refs/item_ids/evidence_refs` são aceitos apenas na fronteira de compatibilidade.

## S21

Os outputs M04 e M05 são validados contra os modelos reais:

- `PersonToolEntitlementPanel`
- `ValidatedPersonContextBundle`

Nenhuma mudança é necessária no loop cognitivo.

## S32/S33

S32 é autoridade de IDs, operações, modos, providers e schemas. S33 é autoridade de readiness e point-in-time. S34 não duplica nenhuma dessas regras.

## P4/P9

S34 produz IDs e versões que S40 poderá incluir nos handoffs suplementares para P4 e P9. Não há conexão direta P3→P5.
