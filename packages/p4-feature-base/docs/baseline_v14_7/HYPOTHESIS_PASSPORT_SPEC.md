# Especificação do passaporte de hipótese

Cada hipótese confirmatória possui YAML em `hypothesis_passports/`.

## Campos obrigatórios

- `hypothesis_id` e família;
- mecanismo econômico;
- observador primário;
- observador de robustez opcional;
- parametrização primária e robustez;
- sinal ou papel esperado;
- condições de aceitação P4;
- protocolo de confirmação P5;
- auditoria P9;
- status e geração.

## Regra de mudança

Alterar fórmula, universo, cutoff, normalização ou parâmetro fora da robustez pré-registrada cria nova versão e nova tentativa.
