# Política de múltiplos testes e holdout

## Três ambientes

1. `DEVELOPMENT`: construção e debugging; não produz conclusão final.
2. `CONFIRMATION`: hipóteses congeladas, validação temporal e correção de multiplicidade.
3. `SEALED_HOLDOUT`: acesso único por release candidate e autoridade P9.

## Hierarquia

Família → perspectiva → observador → parametrização. Um filho não é promovido se o pai não possui evidência.

## Métodos planejados

- exploração: controle de FDR dentro de família;
- confirmação: stepdown dependente/resampling;
- estratégia final: reality-check/SPA e Sharpe deflacionado quando aplicável;
- métricas econômicas só em P5/P9.

## Proibições

- abrir holdout para ajustar fórmula;
- excluir tentativas negativas do denominador;
- reportar a melhor janela como se fosse pré-definida;
- misturar seleção e avaliação no mesmo fold.
