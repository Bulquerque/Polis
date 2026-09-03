# P3.S33 — Point-in-Time Data Boundary & Provenance

## Missão

Criar a única fronteira autorizada entre as ferramentas da extensão e os dados produzidos por P1/P2. A subfase não executa ferramentas de domínio: ela qualifica views, custódia, visibilidade temporal, vintages, identidade e ports read-only.

## Ordem

```text
M01 P2 research views
  └─ M02 P1 custody references
M01 + M02 + S32 snapshot
  └─ M03 PIT and vintage firewall
M01 + M03 + entity sources
  └─ M04 temporal entity resolution
M01–M04 + S32 snapshot
  └─ M05 boundary bundle and preflight
```

## Autoridades

- P1: bytes originais, snapshots, hashes e custódia.
- P2: semântica, identidade, qualidade e `available_at`.
- S33: autorização de consulta, prova temporal, proveniência e resolução temporal.
- S35–S39: consumo dos ports produzidos por S33.
- S40: construção dos adapters executáveis contra os ports.

## Regra temporal

```text
available_at <= decision_time
request.as_of == decision_time
```

A filtragem ocorre antes de busca, ranking, cálculo, comparação ou timeline.

## Limites

S33 não acessa rede, não abre path fornecido pelo LLM, não devolve bytes ao prompt, não cria features, sinais, rankings, portfólios ou backtests e não consulta P5.

## Referências técnicas

- FRED/ALFRED vintage dates: https://fred.stlouisfed.org/docs/api/fred/series_observations.html
- FRED series vintage dates: https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html
- W3C PROV-O: https://www.w3.org/TR/prov-o/
- OpenLineage object model: https://openlineage.io/docs/spec/object-model/
- OpenLineage specification repository: https://github.com/OpenLineage/OpenLineage
