# Parte 1 — Dados e Ingestão Point-in-Time
# Parte 1 — Dados e Ingestão Point-in-Time

## Função do diagrama
A Parte 1 representa a camada de entrada bruta do sistema. Ela coleta e organiza fontes antes de qualquer modelagem. Seu papel é garantir que todo dado tenha origem, data de referência, data de disponibilidade e rastro de versionamento.

## O que entra
Entram dados de mercado, opções, ativos-base, benchmarks, calendários, eventos corporativos, macroeconomia Brasil/EUA e outras fontes relevantes. A lógica é não confiar em dado sem metadata temporal.

## O que a Parte 1 produz
Ela produz zonas raw/bronze, manifesto de dados, registro de fontes e lineage inicial. O principal não é limpar profundamente, mas preservar o dado bruto de forma auditável.

## Ponto crítico
O campo `available_at` é central. Sem ele, o sistema não consegue garantir que uma informação estava de fato disponível no momento do backtest.

## O que a Parte 1 não faz
Ela não limpa profundamente, não calcula features, não prevê retorno, não cria candidatos e não faz ranking. A saída correta é para a Parte 2, que faz qualidade, harmonização e point-in-time formal.
