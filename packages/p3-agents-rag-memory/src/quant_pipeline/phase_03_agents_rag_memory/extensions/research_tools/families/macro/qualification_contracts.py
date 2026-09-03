from __future__ import annotations

from pydantic import Field

from ._compat import MacroToolModel
from .types import NonEmptyStr, QualificationStatus, Sha256


class HandlerSpec(MacroToolModel):
    tool_id: NonEmptyStr
    operation_id: NonEmptyStr
    handler_id: NonEmptyStr
    request_model: NonEmptyStr
    supported_modes: tuple[NonEmptyStr, ...]
    required_views: tuple[NonEmptyStr, ...]
    read_only: bool = True
    point_in_time_safe: bool = True


class HandlerBundleManifest(MacroToolModel):
    schema_id: NonEmptyStr
    schema_version: str = "1.0.0"
    bundle_id: NonEmptyStr
    tool_id: NonEmptyStr
    handlers: tuple[HandlerSpec, ...]
    content_hash: Sha256


class OperationModeQualification(MacroToolModel):
    tool_id: NonEmptyStr
    operation_id: NonEmptyStr
    mode_id: NonEmptyStr
    status: QualificationStatus
    reason_codes: tuple[str, ...]
    required_views: tuple[NonEmptyStr, ...]
    test_targets: tuple[NonEmptyStr, ...]


class OperationModeQualificationPanel(MacroToolModel):
    schema_id: str = "p3.s37.operation_mode_qualification.v1"
    schema_version: str = "1.0.0"
    snapshot_id: NonEmptyStr
    records: tuple[OperationModeQualification, ...]
    content_hash: Sha256


class MacroToolReadinessReport(MacroToolModel):
    schema_id: str = "p3.s37.macro_tool_readiness_report.v1"
    schema_version: str = "1.0.0"
    snapshot_id: NonEmptyStr
    status: QualificationStatus
    available_tool_operations: tuple[NonEmptyStr, ...]
    blocked_tool_operation_modes: tuple[NonEmptyStr, ...]
    reason_codes: tuple[str, ...]
    content_hash: Sha256
