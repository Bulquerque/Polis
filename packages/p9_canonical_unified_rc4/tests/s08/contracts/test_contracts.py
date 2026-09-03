from datetime import UTC, datetime, timedelta, timezone
import pytest
from pydantic import ValidationError

from quant_pipeline.phase_09.subphases.s07_prospective_validation.contracts import IntegrityEnvelope, ModuleStatus
from quant_pipeline.phase_09.subphases.s08_attribution.contracts import S8ConsumerReceipt, S8ModuleExecutionReceipt, S8SubphaseExecutionReceipt

H="a"*64
NOW=datetime(2026,1,1,tzinfo=UTC)


def _receipt(module="P9.S8.M01", status=ModuleStatus.SUCCESS):
    return S8ModuleExecutionReceipt(module_id=module,status=status,input_artifact_ids=("i",),output_artifact_ids=("o",),reason_codes=("P9_TEST",) if status in {ModuleStatus.INVALID,ModuleStatus.FAILED} else (),started_at=NOW,completed_at=NOW,diagnostics_sha256=H,integrity=IntegrityEnvelope(payload_sha256=H))


def test_consumer_partition_must_be_exact():
    with pytest.raises(ValidationError):
        S8ConsumerReceipt(consumer_module_id="P9.S8.M01",source_contract_name="x",source_contract_version="1",source_bundle_sha256=H,input_ref_ids=("a",),accepted_ref_ids=("a",),rejected_ref_ids=("a",))


def test_receipt_rejects_non_utc():
    with pytest.raises(ValidationError):
        S8ModuleExecutionReceipt(module_id="P9.S8.M01",status=ModuleStatus.SUCCESS,input_artifact_ids=("i",),output_artifact_ids=("o",),started_at=datetime.now(timezone(timedelta(hours=1))),completed_at=datetime.now(timezone(timedelta(hours=1))),diagnostics_sha256=H,integrity=IntegrityEnvelope(payload_sha256=H))


def test_subphase_conserves_modules():
    with pytest.raises(ValidationError):
        S8SubphaseExecutionReceipt(expected_module_ids=("P9.S8.M01","P9.S8.M02"),module_receipts=(_receipt(),),status=ModuleStatus.SUCCESS,output_artifact_ids=("o",),integrity=IntegrityEnvelope(payload_sha256=H))


def test_success_subphase_rejects_invalid_child():
    with pytest.raises(ValidationError):
        S8SubphaseExecutionReceipt(expected_module_ids=("P9.S8.M01",),module_receipts=(_receipt(status=ModuleStatus.INVALID),),status=ModuleStatus.SUCCESS,output_artifact_ids=("o",),integrity=IntegrityEnvelope(payload_sha256=H))


def test_consumer_partition_must_cover_all_inputs():
    with pytest.raises(ValidationError):
        S8ConsumerReceipt(consumer_module_id="P9.S8.M01",source_contract_name="x",source_contract_version="1",source_bundle_sha256=H,input_ref_ids=("a","b"),accepted_ref_ids=("a",))


def test_reserved_refs_require_reason_codes():
    with pytest.raises(ValidationError):
        S8ConsumerReceipt(consumer_module_id="P9.S8.M01",source_contract_name="x",source_contract_version="1",source_bundle_sha256=H,input_ref_ids=("a",),accepted_ref_ids=(),reserved_ref_ids=("a",))


def test_receipt_rejects_reverse_clock():
    with pytest.raises(ValidationError):
        S8ModuleExecutionReceipt(module_id="P9.S8.M01",status=ModuleStatus.SUCCESS,input_artifact_ids=("i",),output_artifact_ids=("o",),started_at=NOW,completed_at=NOW-timedelta(seconds=1),diagnostics_sha256=H,integrity=IntegrityEnvelope(payload_sha256=H))


def test_success_receipt_requires_output():
    with pytest.raises(ValidationError):
        S8ModuleExecutionReceipt(module_id="P9.S8.M01",status=ModuleStatus.SUCCESS,input_artifact_ids=("i",),output_artifact_ids=(),started_at=NOW,completed_at=NOW,diagnostics_sha256=H,integrity=IntegrityEnvelope(payload_sha256=H))


def test_invalid_receipt_requires_reason():
    with pytest.raises(ValidationError):
        S8ModuleExecutionReceipt(module_id="P9.S8.M01",status=ModuleStatus.INVALID,input_artifact_ids=("i",),output_artifact_ids=("o",),started_at=NOW,completed_at=NOW,diagnostics_sha256=H,integrity=IntegrityEnvelope(payload_sha256=H))


def test_duplicate_module_receipt_rejected():
    with pytest.raises(ValidationError):
        S8SubphaseExecutionReceipt(expected_module_ids=("P9.S8.M01",),module_receipts=(_receipt(),_receipt()),status=ModuleStatus.SUCCESS,output_artifact_ids=("o",),integrity=IntegrityEnvelope(payload_sha256=H))


def test_failed_child_requires_failed_subphase():
    with pytest.raises(ValidationError):
        S8SubphaseExecutionReceipt(expected_module_ids=("P9.S8.M01",),module_receipts=(_receipt(status=ModuleStatus.FAILED),),status=ModuleStatus.INVALID,output_artifact_ids=("o",),integrity=IntegrityEnvelope(payload_sha256=H))
