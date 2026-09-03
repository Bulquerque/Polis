# P3 Research Tools Unified RC3 — validação final

**Data:** 2026-08-04  
**Pacote:** `P3_RESEARCH_TOOLS_UNIFIED_RC3`  
**Escopo:** hardening final dos 47 módulos S32–S40 e regressão completa da P3.

## Resultado executivo

O RC3 passou em **913/913 testes**, distribuídos em **37/37 partições isoladas**, todas com código de saída zero. A matriz usa um novo processo Python por partição, timeout explícito e contagem agregada. Isso elimina a ambiguidade de encerramento observada quando toda a suíte legada é executada em um único interpretador.

## Cobertura da validação

- Contratos canônicos e executor: aprovados.
- Fundação, integração final e runtime: aprovados.
- Testes específicos das subfases: aprovados.
- Research tools S32–S40: aprovados.
- Testes de hardening RC3: **8/8 aprovados**.
- Compilação completa de `src/` e `tools/`: aprovada.
- Registry legado: **81 módulos**.
- Registry da extensão: **47 módulos**.
- Registry executável: **128 módulos**.
- Famílias: **6**; operações canônicas: **34**.
- DAG da extensão: **47 nós**, **123 arestas internas**, sem ciclos.

## Novas garantias do RC3

1. Inputs opcionais usados pelo código devem estar declarados no contrato e no wrapper.
2. Leitura direta de inputs não declarados é detectada por auditoria AST.
3. Todos os 47 contratos possuem a superfície documental operacional completa.
4. Corpus não pode combinar snapshot, readiness, policy, budget ou qualification divergentes.
5. Surface diagnostics de opções não são liberados sem histórico de contratos.
6. Strikes inválidos e duplicados não quebram o alinhamento com preços e IVs.
7. Macro não aceita divergência de snapshot, contagem de séries, vintages ou referências de contexto.
8. Reverse DCF fora dos limites não produz falsa precisão: retorna bound, residual e estado degradado.
9. Faixas de capacidade dos agentes são estritamente crescentes e não se sobrepõem.
10. A matriz oficial de testes é isolada, reproduzível e fail-fast.

## Estado de produção

O pacote está **qualificado localmente e fail-closed**. Cobertura real de chains históricas, vintages macro, XBRL/restatements e corpus externo depende dos snapshots entregues por P1/P2. Quando essa evidência não existe, a operação permanece `DEGRADED` ou `BLOCKED_UPSTREAM`; o RC3 não fabrica disponibilidade.

A promoção de produção continua proibida dentro da P3 e reservada exclusivamente à autoridade P0.
