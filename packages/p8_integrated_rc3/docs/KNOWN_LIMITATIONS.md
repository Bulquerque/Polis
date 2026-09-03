# Limitações Conhecidas — RC2

1. **Sem qualificação econômica:** integração técnica e correção contratual não provam lucratividade ou segurança econômica em produção.
2. **P9 vNext externa ausente:** S10 valida e constrói o handoff, mas o consumer final precisa ser testado no monorepo global.
3. **P0 externo ausente:** a release não autoriza sua própria promoção.
4. **Facades legadas:** packages com nomes de agentes permanecem como compatibilidade temporária.
5. **Option proxy:** a fronteira S2→S4 pode usar repricing europeu para opção não europeia somente quando explicitamente autorizado; o resultado é degradado, nunca exato.
6. **Margem:** modelos podem ser broker-exact, SPAN-like ou conservadores; a fidelidade precisa ser declarada.
7. **FX:** accounting multi-moeda exige taxa funcional explícita e registrada; não existe conversão implícita.
8. **Lint/typing externo:** `ruff` e `mypy` não estão instalados neste ambiente. Compilação, schemas, testes e verificações AST foram executados; lint/typing devem ser repetidos no CI completo.
9. **Cobertura de branches:** a release possui 93,11% de statement coverage e 75,26% de branch coverage. Os bloqueadores corrigidos possuem regressões específicas, mas o alvo global aspiracional de branches ainda não foi alcançado em todos os adapters e caminhos auxiliares.
10. **Full live golden thread:** não há broker ou market adapter live nesta release.
11. **Produção:** `production_promotion_allowed=false` em todos os relatórios finais.
12. **Compatibilidade RC3 ranqueada:** o bridge fecha ingestão, lineage e contratos até o universo estático S2. Candidatos cuja P6 RC3 não publica lifecycle, liquidez-capacity ou prova econômica suficiente permanecem bloqueados de forma explícita; compatibilidade não significa autorização automática de execução.
13. **Escopo de versão:** a compatibilidade é qualificada contra `P5 0.34.1rc4`, `P6 0.6.2rc4` e `P7 2.3.1rc3`. Mudanças futuras dos produtores exigem novo consumer test ou nova versão do bridge.
