# INPUT_CONTRACTS — phase_02_quality_pit — RC4.1

## Required inputs
- `handoff_manifest_to_phase_2`
- `source_registry`
- `raw_file_inventory`
- `source_snapshot_registry`
- `raw_readability_report`
- `raw_schema_hint_report`
- `ingestion_error_report`

## Rules
- required_inputs_must_exist_for_first_cycle
- optional_feedback_only_when_previous_cycle_validated
- optional_feedback_absence_must_not_block_first_cycle
