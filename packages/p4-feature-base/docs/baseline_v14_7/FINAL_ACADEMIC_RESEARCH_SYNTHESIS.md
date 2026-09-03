# Síntese acadêmica final — theory-first

## Conclusão

A P4 deve ser ampla em mecanismos, mas estreita em graus de liberdade. A literatura de replicação, factor zoo, informação incremental e seleção pós-teste não sustenta implementar centenas de variantes como hipóteses independentes. A arquitetura final mantém dez famílias e 132 arquétipos como cobertura, mas autoriza somente 32 hipóteses fundamentais no caminho confirmatório.

## Decisões científicas

1. **Teoria antes da fórmula.** Toda hipótese possui mecanismo, sinal esperado, horizonte, falhas, dados e família de multiplicidade.
2. **Perspectivas realmente diferentes.** Fonte, mecanismo e padrão de erro distintos contam como diversidade; janelas 20/21/22 não contam.
3. **Parcimônia hierárquica.** Família→perspectiva→observador→parâmetro define o orçamento de testes.
4. **Incrementalidade é downstream.** P4 mede integridade e redundância sem labels; P5 mede capacidade preditiva e ganho incremental.
5. **Representação não substitui observadores.** Matriz interpretável obrigatória, Sparse PCA champion e encoder opcional.
6. **Toda tentativa conta.** O ledger inclui resultados negativos, configurações abandonadas, notebooks e agentes paralelos.
7. **Missingness é informação.** Ausência, indisponibilidade, não aplicabilidade e atraso são estados separados.
8. **Temporalidade é parte da fórmula.** Vintages, publication time, availability e fit cutoffs são campos contratuais.

## Implicações por família

- Momentum: absoluto, cross-sectional, residual e confirmado; demais variações são extensão.
- Reversão: pressão curta, desvio robusto e residual; pares dependem de gate adicional.
- Fundamentos: value, profitability, investment e accrual quality com vintages reais.
- Liquidez: participação, impacto e atenção separados.
- Risco: estado multiescala, downside, drawdown e risco implícito separados.
- Sistema: downside beta, concentração comum e connectedness direcional.
- Carry: curva, basis e ranking cross-asset com convenções por classe.
- Macro: estados conjuntos e surpresas em tempo de publicação.
- Eventos: surpresa e drift não são o mesmo observador.
- Narrativa: direção, novidade, reach, credibilidade, disagreement e mudança narrativa permanecem desacoplados.

## Representações

PCA/Sparse PCA por família é o baseline de produção documental. O encoder só é autorizado quando houver evidência de estrutura não linear/multi-view material, amostra suficiente e aprovação de orçamento. Ele é raso, self-supervised, cross-fitted e limitado a duas configurações. Qualquer objetivo de retorno, IC, Sharpe ou forecast pertence à P5.

## Inferência

Exploração e confirmação são separadas. P5 aplica validação temporal aninhada e correções por família. P9 usa holdout selado, ledger completo e avaliação pós-seleção. A matriz completa de evidências está em `registries/ACADEMIC_EVIDENCE_MATRIX.csv` e as referências em `registries/LITERATURE_REGISTRY.csv`.
