# P3.S34 — Research Capability, Depth & Planning

## Missão

Converter características **ex ante** das personas em capacidades, recursos, planos de pesquisa e permissões de ferramentas compatíveis com o runtime S21. A subfase não executa as ferramentas; ela define o que cada pessoa pode pedir, em qual profundidade e sob quais limites.

## Ordem canônica

```text
M01 Taxonomia e requisitos operação × modo
  └─ M02 Perfil ex ante por pessoa
M01 + S32 + S33
  └─ M03 Planos DAG e readiness
M02 + M03 + S15/S16 + S33
  └─ M04 Entitlement no contrato exato de S21
M04 + S20 + catálogo S32
  └─ M05 Contexto S20 → S21 com descriptors autorizados
```

## Princípios

1. Não existe nível global da pessoa.
2. Acesso, competência, método e recursos são dimensões diferentes.
3. Performance, PnL, retorno futuro, ranking e outcomes não podem definir entitlement.
4. O máximo é cinco chamadas visíveis por pessoa/ciclo.
5. Uma operação indisponível na S33 fica bloqueada, mesmo que a persona seja competente.
6. O LLM escolhe somente entre operações e modos previamente autorizados.
7. S20 e S21 permanecem intactos; M05 realiza a projeção explícita entre os contratos.

## Módulos

- `P3.S34.M01 research_capability_taxonomy_builder`
- `P3.S34.M02 person_research_capability_profiler`
- `P3.S34.M03 research_plan_template_registry_builder`
- `P3.S34.M04 effective_entitlement_overlay_builder`
- `P3.S34.M05 person_context_tool_descriptor_overlay_builder`

## Autoridades

- S7/S14/S20: população, identidade, personalidade e contexto já validados.
- S15/S16: limites legados e política de gateway.
- S32: catálogo, operações, modos, providers e schemas.
- S33: readiness de dados e bloqueios upstream.
- S34: capacidade ex ante, planos, entitlement e descriptors.
- S21: cognição e chamadas; consumidor dos overlays de S34.

## Fundamentação aplicada

- MRKL: módulos especializados atrás de uma interface de raciocínio.
- ReAct: alternância entre interpretação, ação e observação.
- Toolformer: seleção estruturada de APIs e incorporação de resultados.
- Racionalidade limitada/rational inattention: pesquisa condicionada por custo, atenção e acesso.
- JSON Schema 2020-12 e Pydantic: contratos estritos e descriptors derivados dos mesmos modelos.

## Limites

S34 não usa rede, não executa handlers, não consulta P5, não lê arquivos de P1/P2, não produz sinal, feature, portfólio ou backtest e não aprende com outcomes no mesmo ciclo.
