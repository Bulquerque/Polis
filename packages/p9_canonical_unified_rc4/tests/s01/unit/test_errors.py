from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.errors import (
    ContractError,
    IntegrityError,
    LineageIntegrityError,
    P9S1Error,
    ReplayError,
)


def test_typed_errors_preserve_message_and_hierarchy() -> None:
    for error_type in (ContractError, IntegrityError, LineageIntegrityError, ReplayError):
        error = error_type("diagnostic")
        assert isinstance(error, P9S1Error)
        assert isinstance(error, RuntimeError)
        assert str(error) == "diagnostic"
