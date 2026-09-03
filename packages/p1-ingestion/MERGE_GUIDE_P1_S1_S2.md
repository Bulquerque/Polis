# Merge Guide — P1.S1 + P1.S2

## Base esperada
Aplicar sobre o diretório:
`phase_01_ingestion/phase_01_ingestion_agent_package_RC4_1/`
proveniente do `New Version.zip` fornecido como baseline desta reforma.

## Regra de merge
1. Preservar a topologia pública da P1 e os IDs de módulo existentes.
2. Copiar os arquivos deste pacote mantendo caminhos relativos.
3. Não substituir as novas pastas `providers/` e `transport/` por implementações paralelas.
4. Reformas posteriores de S3–S5 devem consumir `capture_id`, `attempts`, `run_id` e os timestamps já adicionados, em vez de recriar conceitos incompatíveis.
5. Após juntar outras subfases, regenerar `MANIFESTO.csv` novamente para o estado combinado final.

## Arquivos centrais introduzidos
- `src/quant_pipeline/phase_01_ingestion/core.py`
- `src/quant_pipeline/phase_01_ingestion/capture_model.py`
- `src/quant_pipeline/phase_01_ingestion/providers/`
- `src/quant_pipeline/phase_01_ingestion/transport/`

## Compatibilidade
- S1/S2 mantêm os mesmos nomes de outputs públicos.
- `records` continua compatível com S3–S5 atuais no caminho feliz.
- `attempts` é a nova superfície para error lifecycle/partial success nas reformas seguintes.

## Não fazer ao integrar
- Não voltar a usar `source_id` como identidade única de captura.
- Não materializar API keys em registry/tasks/artifacts.
- Não colapsar `reference_time` em `available_at`.
- Não mover normalização econômica para a P1.
- Não criar outro HTTP client, credential resolver ou adapter registry paralelo.
