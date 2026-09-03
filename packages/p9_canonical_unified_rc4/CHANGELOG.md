# Changelog

## 0.1.0rc4.post2 — Hardened 5

- closed PIT leakage in executed outcomes;
- enforced committed scientific and compute budgets;
- bound prospective materialized records to upstream evidence;
- bound target configuration, trial family, attribution and promotion receipts;
- hardened release certification against cross-run or empty evidence;
- made S7 hashing deterministic across `PYTHONHASHSEED`;
- regenerated fixtures, registries and qualification evidence;
- reproduced 587 passed / 7 external skips and current coverage.

## 0.1.0rc4

- isolou toda compatibilidade externa em `phase_09.compatibility`;
- congelou e verificou fingerprints dos snapshots qualificados de P0–P8;
- implementou publisher nativo P8→P9 com perfis LIMITED e FULL fail-closed;
- corrigiu canonicalização do feedback P9/P0→P8 e qualificou o loader real da P8;
- implementou validação real dos reports da P9 pelos normalizadores e schema da P0;
- integrou P3 em processo isolado nos dois sentidos sem copiar contratos;
- qualificou consumers reais de feedback de P5, P7 e P8 RC4.1;
- manteve P6 como feedback governado por P0 por ausência de consumer direto;
- adicionou snapshots de schemas externos ligados aos fingerprints de P3 e P8;
- proibiu imports estáticos de P0–P8 nos 70 módulos científicos;
- ampliou a suíte da P9 de 567 para 591 testes;
- executou os 631 testes da P8 com a nova P9 presente.

## 0.1.0rc2

- corrigiu o denominador do estimador IPS e o caso de suporte zero no DR;
- tornou receipts e bundles S5/S6 autoconsistentes contra tampering;
- introduziu trial-plan V2 lossless na fronteira S2→S3;
- introduziu evidence envelope V2 S4→S5 com binding de identidade e hashes;
- introduziu stress-capacity envelope V2 S6→S7 com AUM content-addressed;
- introduziu source context V2 S8→S9 com conservação de ciclo e configurações;
- tornou o source cycle explícito na release S9→S10;
- adicionou `P9CycleRunner` fail-closed e golden terminal states;
- removeu asserts de produção e adicionou exceções de domínio;
- adicionou timeout preemptivo POSIX e interfaces de clock/controller;
- adicionou registries globais de contracts, tokens e reason codes;
- regenerou schemas e fixtures para os contratos V2;
- ampliou a qualificação de 547 para 567 testes;
- construiu e validou a wheel `0.1.0rc2`.

## 0.1.0rc1

- consolidou as dez subfases em uma árvore canônica;
- selecionou uma única implementação para cada subfase;
- qualificou a árvore inicial com 547 testes aprovados.
