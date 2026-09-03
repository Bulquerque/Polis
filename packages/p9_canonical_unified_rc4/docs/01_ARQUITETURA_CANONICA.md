# Arquitetura canônica

## Fluxo principal

```text
S1 evidência e maturidade
→ S2 experimentos e hiperparâmetros
→ S3 backtests temporais
→ S4 métricas institucionais
→ S5 bootstrap e seleção estatística
→ S6 stress e capacidade
→ S7 validação prospectiva
→ S8 attribution
→ S9 promoção e feedback
→ S10 memória e release
```

## Authority boundaries

- S1 determina se a evidência pode ser avaliada.
- S2 define e agenda experimentos, sem avaliar o próprio resultado final.
- S3 executa backtests point-in-time.
- S4 calcula métricas; não decide promoção.
- S5 estima incerteza e risco de overfitting.
- S6 avalia fragilidade fora da amostra histórica observada.
- S7 monitora shadow/live e recomenda requalificação ou rollback.
- S8 atribui resultados sem transformar associação em causalidade automática.
- S9 emite recomendação e feedback tipado para ciclos futuros.
- S10 fecha memória de pesquisa e o pacote de release.

## Namespace

Os diretórios `quant_pipeline`, `phase_09` e `subphases` permanecem namespaces implícitos. Cada subfase pode possuir `__init__.py` local para sua API pública, sem bloquear a composição com outras fases.
