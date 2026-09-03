# INPUT_CONTRACTS — phase_01_ingestion — RC4.1

## Required inputs
- `source_registry_config`
- `ingestion_run_config`
- `source_credentials_handle`
- `source_calendar_config`
- `local_raw_file_paths`
- `api_source_definitions`
- `manual_source_definitions`

## Rules
- required_inputs_must_exist_for_first_cycle
- optional_feedback_only_when_previous_cycle_validated
- optional_feedback_absence_must_not_block_first_cycle
