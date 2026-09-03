# Núcleo inicial de variáveis

O catálogo completo possui **132 arquétipos de observadores**. Para evitar bloat e overfitting, a primeira implementação deve começar pelos **83 observadores `CORE`** em `registries/CORE_BASELINE_OBSERVER_SET.csv`.

## Estratégia

- `CORE`: primeira implementação e oracles obrigatórios;
- `EXTENSION`: ativar após disponibilidade/qualidade da modalidade;
- `EXPERIMENTAL`: somente via proposta N+1 e ablation pré-registrada.

O núcleo cobre todas as dez famílias sem exigir que todas as fontes extensionais estejam presentes. Uma família indisponível recebe status explícito, nunca valores artificiais.

## Regra de escala

Cada arquétipo `CORE` implementa uma parametrização primária e no máximo duas escalas adjacentes justificadas. Não se cria uma feature distinta para cada janela arbitrária.

## MVP de 48

O MVP preserva todas as dez famílias e inclui representantes de tendência, reversão, fundamentos, liquidez, cauda, sistema, carry, macro, eventos e narrativa. Ele é o conjunto recomendado para a primeira integração P4→P5.
