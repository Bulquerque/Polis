# Parte 2 — Limpeza, Harmonização, Qualidade e Point-in-Time
# Parte 2 — Limpeza, Harmonização, Qualidade e Point-in-Time

## Função do diagrama
A Parte 2 transforma dados coletados em painéis limpos e sincronizados. Ela é a camada que impede vazamento temporal, duplicidade, inconsistência de chaves e uso indevido de informações futuras.

## Papel no pipeline
A Parte 2 alimenta diretamente a Parte 4 e também alimenta a Parte 3. Isso é importante: fontes externas e contexto que chegam à sociedade de agentes devem estar controlados pelo mesmo padrão de qualidade e disponibilidade temporal.

## Principais tarefas
Inclui parsing, harmonização de tickers, validação de datas, corporate actions, calendário de negociação, deduplicação, missing values, checagem de schemas, `available_at`, `reference_date`, `as_of_date` e alinhamento entre ativos e opções.

## Chaves importantes
Para opções, a chave `contract_key = option_id + expiration_date` é essencial. Sem isso, o sistema pode misturar contratos de vencimentos diferentes, o que invalidaria o backtest.

## O que a Parte 2 não faz
Ela não constrói alpha, não calcula score, não ranqueia e não escolhe carteira. Ela garante que o resto do sistema trabalhe com dados confiáveis, temporais e auditáveis.
