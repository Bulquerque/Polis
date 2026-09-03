# Decisão de arquitetura do encoder

## Veredito

O encoder **não é obrigatório** e não substitui as features interpretáveis ou PCA. Seu status inicial é `OPTIONAL_CHALLENGER`.

## Escada de representações

- Tier 0: matriz interpretável selecionada;
- Tier 1: PCA/Sparse PCA por família;
- Tier 2: encoder raso por família, denoising/masked e shared-private.

P5 deve conseguir operar sem Tier 2.

## Arquitetura permitida

- um encoder por família e grupo de horizonte;
- 1 ou 2 camadas ocultas;
- latent compartilhado da família;
- latents privados por modalidade quando houver views suficientes;
- Huber loss em entradas observadas, balanceada por grupo;
- masking e corrupção leve;
- modality dropout;
- regularização de ortogonalidade shared/private;
- máscaras de missingness como informação explícita.

## Arquiteturas fora do baseline

- autoencoder global único;
- VAE;
- Transformer encoder;
- DCCA/DCCAE completa;
- graph autoencoder;
- encoder supervisionado por retorno.

Elas podem virar propostas N+1, mas não entram no baseline sem evidência de necessidade.

## Promoção

O encoder só deixa de ser challenger se P5/P9 demonstrarem ganho incremental estável contra Tier 0 e Tier 1 em holdout bloqueado, múltiplos períodos/regimes e custo computacional aceitável. Esse gate não é executado pela P4.
