# P3 Research Tools Unified RC2 — validação final

**Data:** 2026-08-04  
**Pacote:** `P3_RESEARCH_TOOLS_UNIFIED_RC2`  
**Escopo:** correção dos 18 módulos vermelhos, integração S32–S40, compatibilidade com o núcleo P3 e fechamento de release.

## Resultado executivo

O RC2 passou em uma matriz completa de **905 testes**, executada em processos independentes para impedir contaminação de recursos entre grupos. Não houve falha de assert, erro de contrato ou regressão funcional.

A execução monolítica de todos os testes em um único processo conclui os casos visíveis, mas o interpretador pode permanecer vivo após o término por interação de encerramento entre grupos assíncronos do conjunto legado. Para não registrar um falso timeout como falha funcional, a validação oficial deste RC2 usa grupos isolados, cada um com código de saída zero.

## Matriz de testes

| Grupo | Resultado |
|---|---:|
| Testes raiz + contratos + foundation contracts + integration runtime | 312/312 |
| Phase-specific, incluindo 79 testes S32–S34 | 227/227 |
| Research tools unified | 66/66 |
| Runtime context, engine, hardening, products e society | 278/278 |
| Scientific evaluation, specifications e final integration | 22/22 |
| **Total** | **905/905** |

## Verificações estruturais

- Registry legado preservado: **81 módulos**.
- Registry da extensão: **47 módulos**.
- Registry executável combinado: **128 módulos**.
- `by_id("P3.S32.M01")` e `by_id("P3.S40.M08")`: resolvidos pelo executor.
- DAG S32–S40: **47 nós**, **123 arestas internas**, sem ciclos.
- Todas as arestas internas usam artefatos realmente produzidos e aceitos pelos contratos.
- Nenhuma ligação direta não autorizada P3→P4 ou P3→P9 foi materializada.
- Handoff P4 permanece candidato não conectado até autorização global.
- Evidência P9 permanece local, `DEFERRED_BY_GOVERNANCE`, com feedback somente em N+1.
- Compilação de `src/`: aprovada.

## Correções principais comprovadas

1. Contratos S37 normalizados; `required` e `optional` não são mais tratados como artefatos.
2. Fronteira S33 materializa ports point-in-time através de fábrica process-local injetada.
3. Bundles familiares preservam políticas, qualificações, readiness e hashes até S40.
4. S40.M01 cria uma única autoridade de registry; S40.M02 consome exatamente essa instância.
5. S40.M03 valida registry, gateway, providers, políticas, aliases, entitlements e snapshots antes do binding S21.
6. A cadeia real S21→S40.M04 produz evidência validada.
7. S40.M05 torna completeness, preflight e receipts obrigatórios bloqueantes.
8. S40.M06/M07 validam consumidores e governança sem inventar conexões externas.
9. S40.M08 fecha a cadeia por hashes e continua fail-closed, sem autoridade de promoção.
10. Executor oficial descobre a extensão sem alterar a autoridade imutável dos 81 módulos legados.

## Critério de release

O pacote só deve ser considerado fechado quando, além desta matriz:

- `tools/release.py manifest` concluir;
- `tools/release.py verify` retornar `PASS` com zero erros;
- o ZIP final passar pelo mesmo `verify` após extração limpa;
- o SHA-256 externo do ZIP for registrado.

Esses resultados são adicionados ao fechamento externo após a geração final do pacote.
