# Fundamentação aplicada

## Real-time macro data

Croushore e Stark mostram que vintages de dados importam para análise e previsão. O Real-Time Data Set for Macroeconomists do Philadelphia Fed preserva o conjunto informacional disponível em diferentes datas.

- https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/real-time-data-set-for-macroeconomists
- https://www.philadelphiafed.org/-/media/frbp/assets/working-papers/2000/wp00-6.pdf

Aplicação na S37: seleção explícita de vintage e bloqueio quando o histórico não está disponível.

## ALFRED/FRED

Os períodos de tempo real e as vintage dates da API oficial fundamentam a separação entre data da observação e data de conhecimento.

Aplicação: `available_at`, `vintage_date`, `revision_id` e políticas de seleção distintas.

## Ports and adapters

As APIs são adaptadas em P1 e normalizadas em P2. A S37 depende de uma porta PIT, evitando acoplamento com HTTP, credenciais ou fornecedores.

## Reprodutibilidade

Snapshots, hashes, schemas estritos e testes metamórficos impedem que dados futuros ou mudanças de ordem alterem uma simulação histórica.
