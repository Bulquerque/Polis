# Changelog

## P6-RC6.2-P5-V2-CLOSURE-RC4

- reconciliou todos os 55 `MODULE_ID`s com o registry;
- reclassificou os geradores term-structure e underlying-overlay como capabilities reservadas;
- separou `INTEGRITY_VALIDATED` de `SEMANTICALLY_CONSUMED`;
- fechou o receipt canônico do contrato `P5-P6-V2`;
- manteve liquidez do subjacente baseada em bid/ask e fail-closed;
- publicou wheel `0.6.2rc4`;
- 85 testes aprovados; produção permanece bloqueada.


## P6-RC6.1-P5-RC34-HARDENED

- implementou consumo nativo do bundle completo P5 RC34;
- tornou obrigatório o manifest para artefatos P5 V2 nativos;
- valida o hash do manifest-pai pelo algoritmo de identidade da P5;
- valida os 11 artefatos por ID, hash, schema, contagem, run, cycle e relógio;
- integrou availability e lineage reports nos receipts;
- converte `return_distributions` em cenários terminais ancorados no spot PIT da P2;
- converte `scenario_paths` em trajetórias quando underlying e horizonte coincidem;
- preserva confidence, abstention, calibration, regime, OOD e ambiguity metadata;
- removeu `horizon_days=1` da geração e incluiu horizonte na identidade do candidato;
- adicionou `p5_handoff_compatibility_report` e referências P5 ao snapshot hash;
- corrigiu o adapter V1 para o formato real RC34, mantendo capability limitada;
- removeu a propriedade de `quant_pipeline/__init__.py` do wheel P6 para evitar colisão com P5;
- validou instalação conjunta P5/P6 nas duas ordens;
- adicionou golden fixture real RC34 e testes de adulteração, abstention, replay e fluxo não vazio;
- atualizou pipeline para `P6-RC6.1-P5-RC34-HARDENED`, schema `6.1.0-rc1` e wheel `0.6.1rc1`.

## Baseline anterior

P6-RC6.0-C-TECHNICAL-CLOSURE, preservada como origem histórica.
