# Artifact Style Guide — V14.1 RC4.1

## Formatos

- Painéis grandes: `.parquet`.
- Contratos: `.yaml`.
- Schemas: `.schema.yaml`.
- Manifests tabulares: `.csv`.
- Relatórios estruturados: `.json`.
- Relatórios humanos: `.md`.
- Logs de execução: `.jsonl`.
- Diagramas: `.mmd` + `.png`.

## Nomeação

- Schema: `<artifact_name>.schema.yaml`.
- Fixture: `<phase_id>_<artifact_name>_sample.<format>`.
- Relatório: `<phase_id>_<report_name>.json` ou `.md`.
- Manifest: `<phase_id>_<manifest_name>.csv`.

## Campos técnicos recorrentes

Sempre que aplicável:

- `pipeline_version`
- `phase_id`
- `module_id`
- `artifact_name`
- `schema_version`
- `lineage_id`
- `created_at`
- `hash`
