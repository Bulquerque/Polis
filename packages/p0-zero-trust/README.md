# Phase 00 — Zero Trust Guardian — V14.1 RC4.1

A Fase 0 é a Guardiã Zero Trust do pipeline. Ela governa contratos, schemas, hashes, lineage, testes, qualidade de código, dashboards técnicos, skills de agentes e release gates.

Ela não participa do fluxo econômico. Ela não limpa dados de mercado, não cria features econômicas, não prevê retorno, não cria candidatos, não ranqueia, não monta carteira e não altera backtest.

## Papel

- Validar se Fases 1–9 estão contratualmente corretas.
- Coletar relatórios técnicos de todas as fases.
- Bloquear releases com falha crítica.
- Produzir dashboards técnicos e evidências Zero Trust.
- Devolver feedback técnico para cada fase.

## Plano econômico preservado

1 → 2; 2 → 3/4/6; 3 → 4; 4 → 5; 5 → 6; 6 → 7; 7 → 8; 8 → 9; 9 → 3.

## Plano Zero Trust

0 ↔ 1–9, apenas por contratos, schemas, hashes, test reports, manifests, dashboards e feedback técnico.

## RC4.1 — política de código limpo e fonte única

Este pacote segue a Fase 0 como Guardiã Zero Trust e espelho derivado para padrões transversais. A autoridade normativa permanece no master global.

- Procurar antes de criar.
- Editar apenas o necessário.
- Não duplicar utilitários comuns.
- Não duplicar testes estruturais globais.
- Manter código específico dentro da fase e código transversal em `quant_pipeline.common`.
- Registrar todo arquivo novo no manifesto.
