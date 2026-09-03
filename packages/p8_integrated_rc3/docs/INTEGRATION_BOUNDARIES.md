# Fronteiras de Integração

## S1/S2 → S3/S4

Implementação: `integration/a1_a2.py`.

A fronteira recebe o resultado point-in-time S1/S2 e bindings explícitos de risco. Ela:

- preserva apenas candidatos encaminhados;
- resolve moeda no nível do candidato;
- transforma pernas P6 em pernas lineares ou options europeias para repricing;
- exige bindings de fatores, spot, volatilidade, taxas e notional;
- permite proxy europeia para option não europeia somente por autorização explícita;
- nunca fabrica Greeks ou liquidez.

## S3/S4 → S5/S6

Implementação: `integration/a2_a3.py`.

A fronteira materializa:

- candidatos com bounds, capital, margem e maximum loss por unidade;
- paths de PnL por cenário;
- stresses obrigatórios;
- preferências ordinais;
- ambiguity opcional para robust shadow;
- contexto de lifecycle por perna.

A fronteira falha se horizontes, candidates, NPZs, bindings ou economics não fecharem.

## S5/S6 → S7/S8

Implementação: `integration/a3_a4.py`.

Esta é a ponte shape/scale:

```text
quantidade final por candidato
× quantidade da perna por unidade
→ alocação virtual por instrumento
→ netting físico
→ target executável por instrumento
```

Ela conserva posições atuais, rejeita cruzamento de zero sem autorização, exige instrument specs e preserva referências para risk gate, hedge e lifecycle.

## S7/S8 → S9/S10

Implementação: `integration/a4_a5.py`.

A ponte converte eventos, ledgers, posições, valuations e dual book em evidência auditável. Para ordens multi-leg, cria projeções por perna para S10 preservando `source_order_id` e `source_fill_id`.

## S9 → S7/S8

A decisão de segurança vira um `RuntimeControlCommand` enriquecido, aplicado pela mesma máquina de estados da execução. S9 não chama broker diretamente.

## Invariantes globais

- nenhum candidato desaparece;
- nenhuma quantidade desaparece;
- nenhum fill existe sem ordem;
- soma virtual por instrumento = posição física atribuída;
- score ordinal não vira retorno;
- available_at e clocks são validados;
- hashes são verificados antes da transformação;
- erro de integridade não vira fallback estatístico.
