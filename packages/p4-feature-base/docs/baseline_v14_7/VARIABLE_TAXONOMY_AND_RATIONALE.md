# Taxonomia de variáveis e racional econômico

## Estrutura de cada variável

Cada variável deve ser definida como:

`fenômeno → perspectiva → observador → parametrização → realização`.

A documentação deve distinguir mecanismo econômico de fonte de dados e técnica estatística.

## F01 — Momentum, tendência e persistência

Inclui momentum cross-sectional e time-series, slope robusto, breakout, persistência, aceleração, residualização, confirmação por volume, opções e narrativa. Mantém horizontes separados porque continuação curta, média e longa não são o mesmo efeito.

## F02 — Reversão e valor relativo

Inclui reversão curta, overreaction longa, distância de tendência, residual de mercado/setor, pares, cointegração e posição em cluster. O módulo deve separar desvio transitório de mudança estrutural.

## F03 — Value, qualidade, profitability e investment

Inclui múltiplos de preço, gross/operating profitability, margens, asset growth, investimento, accruals, leverage e fundamental momentum. Todo dado contábil deve respeitar publicação, lag regulatório e vintage.

## F04 — Liquidez, atenção e crowding

Inclui turnover, Amihud, spread, volume anormal, staleness, atenção de notícias, concentração de open interest e consenso. Liquidez e atenção não são sinônimos; o conflito entre atenção alta e negociabilidade baixa é uma feature própria.

## F05 — Risco realizado, cauda e assimetria

Inclui volatilidade multiescala, semivariância, drawdown, skewness, kurtosis, jumps, vol-of-vol, expected-shortfall proxies, common tail risk e variance risk premium. O objetivo é representar a distribuição, não apenas a média.

## F06 — Risco sistemático, sistêmico e connectedness

Inclui beta, downside beta, correlação parcial, market mode, effective rank, variance-decomposition connectedness, centralidade e proxies de CoVaR/SRISK quando inputs apropriados existirem. Distingue risco do ativo de contribuição ao risco do sistema.

## F07 — Carry, curva, basis e cross-asset

Inclui slope, curvature, roll-down, futures basis, dividend carry, option term structure e diferenciais entre ativos. Cada classe precisa de convenções próprias; não existe uma fórmula universal de carry.

## F08 — Macro, ciclo e regime

Inclui nível, mudança, aceleração, surpresa, curva, condições financeiras, crédito, energia e distância histórica do estado. P4 descreve o regime contemporâneo; probabilidades futuras pertencem à P5.

## F09 — Eventos, surpresa e sazonalidade

Inclui tempo até/depois do evento, reação, decaimento, post-earnings state, corporate actions, vencimentos e sazonalidade. A feature deve carregar calendário e timestamp de disponibilidade.

## F10 — Narrativa, evidência e desacordo

Inclui direção, força, credibilidade, novidade, contradição, disagreement, polarização, diversidade de hipóteses, mudança narrativa e força da visão minoritária. Não reduzir tudo a um sentimento médio.

## Política de parâmetros

As janelas são banks teóricos pequenos. Cada observador pode ter no máximo quatro variantes, preferencialmente três. P4 preserva variantes estruturais e remove apenas problemas de qualidade/redundância; P5 decide utilidade preditiva com validação temporal.
