from __future__ import annotations

from collections.abc import Iterable

from .canonical import content_hash
from .models import (
    CorpusIndexReadinessReport,
    CorpusIndexSnapshot,
    CorpusMode,
    CorpusOperationQualificationPanel,
    CorpusToolReadinessReport,
    HandlerBundleManifest,
    HandlerSpec,
    OperationModeQualification,
    QualificationStatus,
)

VERSION_GRAPH_REASON = "P3_RT_QUAL_VERSION_GRAPH_UNAVAILABLE"
PARTIAL_PROVENANCE_REASON = "P3_RT_DATA_PROVENANCE_PARTIAL"


class CorpusQualificationBuilder:
    def document_bundle(
        self,
        *,
        snapshot: CorpusIndexSnapshot,
        readiness: CorpusIndexReadinessReport,
        version_graph_available: bool,
        p1_provenance_available: bool,
    ) -> tuple[HandlerBundleManifest, CorpusOperationQualificationPanel]:
        specs = (
            self._spec("search", "SearchCorpusRequest", tuple(CorpusMode)),
            self._spec("get_document", "GetDocumentRequest", tuple(CorpusMode)),
            self._spec(
                "compare_versions",
                "CompareVersionsRequest",
                (CorpusMode.STANDARD, CorpusMode.TRIANGULATED, CorpusMode.FORENSIC),
            ),
            self._spec(
                "inspect_provenance",
                "InspectProvenanceRequest",
                tuple(CorpusMode),
            ),
        )
        records = tuple(
            self._document_qualification(
                spec=spec,
                mode=mode,
                readiness=readiness,
                version_graph_available=version_graph_available,
                p1_provenance_available=p1_provenance_available,
            )
            for spec in specs
            for mode in spec.supported_modes
        )
        return self._manifest(snapshot, "document", specs), self._panel(snapshot, records)

    def reasoning_bundle(
        self,
        *,
        snapshot: CorpusIndexSnapshot,
        readiness: CorpusIndexReadinessReport,
        version_graph_available: bool,
    ) -> tuple[HandlerBundleManifest, CorpusOperationQualificationPanel]:
        specs = (
            self._spec(
                "find_counterevidence",
                "FindCounterevidenceRequest",
                (CorpusMode.STANDARD, CorpusMode.TRIANGULATED, CorpusMode.FORENSIC),
            ),
            self._spec(
                "build_timeline",
                "BuildTimelineRequest",
                (CorpusMode.LOOKUP, CorpusMode.STANDARD, CorpusMode.TRIANGULATED),
            ),
        )
        records = tuple(
            self._reasoning_qualification(
                spec=spec,
                mode=mode,
                readiness=readiness,
                version_graph_available=version_graph_available,
            )
            for spec in specs
            for mode in spec.supported_modes
        )
        return self._manifest(snapshot, "reasoning", specs), self._panel(snapshot, records)

    def consolidate(
        self,
        *,
        snapshot: CorpusIndexSnapshot,
        readiness: CorpusIndexReadinessReport,
        document_bundle: HandlerBundleManifest,
        reasoning_bundle: HandlerBundleManifest,
        panels: Iterable[CorpusOperationQualificationPanel],
    ) -> tuple[
        HandlerBundleManifest,
        CorpusOperationQualificationPanel,
        CorpusToolReadinessReport,
    ]:
        panel_items = tuple(panels)
        if any(item.snapshot_id != snapshot.snapshot_id for item in panel_items):
            raise ValueError("corpus qualification panel snapshot_id mismatch")
        handlers = tuple(
            sorted(
                (*document_bundle.handlers, *reasoning_bundle.handlers),
                key=lambda item: item.operation_id,
            )
        )
        operation_ids = [item.operation_id for item in handlers]
        if len(operation_ids) != len(set(operation_ids)):
            raise ValueError("duplicate corpus handler operation_id")
        records = tuple(
            sorted(
                (record for panel in panel_items for record in panel.records),
                key=lambda item: (item.operation_id, item.mode_id.value),
            )
        )
        actual_keys = [(item.operation_id, item.mode_id) for item in records]
        if len(actual_keys) != len(set(actual_keys)):
            raise ValueError("duplicate corpus operation/mode qualification")
        expected_keys = {
            (handler.operation_id, mode)
            for handler in handlers
            for mode in handler.supported_modes
        }
        if set(actual_keys) != expected_keys:
            raise ValueError("corpus handler and qualification coverage mismatch")
        manifest = self._manifest(snapshot, "complete", handlers)
        panel = self._panel(snapshot, records)
        report = self._readiness_report(snapshot, readiness, records)
        return manifest, panel, report

    def _document_qualification(
        self,
        *,
        spec: HandlerSpec,
        mode: CorpusMode,
        readiness: CorpusIndexReadinessReport,
        version_graph_available: bool,
        p1_provenance_available: bool,
    ) -> OperationModeQualification:
        status = self._base_status(readiness)
        reasons: list[str] = []
        if mode is CorpusMode.FORENSIC and not version_graph_available:
            status = QualificationStatus.BLOCKED_UPSTREAM
            reasons.append(VERSION_GRAPH_REASON)
        if spec.operation_id == "inspect_provenance" and not p1_provenance_available:
            if status is QualificationStatus.QUALIFIED_LOCAL:
                status = QualificationStatus.DEGRADED
            reasons.append(PARTIAL_PROVENANCE_REASON)
        return self._qualification(spec.operation_id, mode, status, reasons)

    def _reasoning_qualification(
        self,
        *,
        spec: HandlerSpec,
        mode: CorpusMode,
        readiness: CorpusIndexReadinessReport,
        version_graph_available: bool,
    ) -> OperationModeQualification:
        status = self._base_status(readiness)
        reasons: list[str] = []
        if (
            spec.operation_id == "find_counterevidence"
            and mode is CorpusMode.FORENSIC
            and not version_graph_available
        ):
            status = QualificationStatus.BLOCKED_UPSTREAM
            reasons.append(VERSION_GRAPH_REASON)
        return self._qualification(spec.operation_id, mode, status, reasons)

    @staticmethod
    def _readiness_report(
        snapshot: CorpusIndexSnapshot,
        readiness: CorpusIndexReadinessReport,
        records: tuple[OperationModeQualification, ...],
    ) -> CorpusToolReadinessReport:
        failed = [item for item in records if item.status is QualificationStatus.FAILED]
        blocked = tuple(
            f"{item.operation_id}:{item.mode_id.value}"
            for item in records
            if item.status is QualificationStatus.BLOCKED_UPSTREAM
        )
        available = tuple(
            sorted(
                {
                    item.operation_id
                    for item in records
                    if item.status
                    in {
                        QualificationStatus.QUALIFIED_LOCAL,
                        QualificationStatus.DEGRADED,
                    }
                }
            )
        )
        if failed or readiness.status is QualificationStatus.FAILED:
            status = QualificationStatus.FAILED
        elif blocked:
            status = QualificationStatus.DEGRADED
        else:
            status = QualificationStatus.QUALIFIED_LOCAL
        reasons = tuple(
            sorted(
                {
                    *readiness.reason_codes,
                    *(reason for item in records for reason in item.reason_codes),
                }
            )
        )
        base = {
            "snapshot_id": snapshot.snapshot_id,
            "status": status,
            "available_operations": available,
            "blocked_operation_modes": blocked,
            "reason_codes": reasons,
        }
        return CorpusToolReadinessReport(content_hash=content_hash(base), **base)

    @staticmethod
    def _base_status(readiness: CorpusIndexReadinessReport) -> QualificationStatus:
        if not readiness.lexical_ready or not readiness.point_in_time_filter_ready:
            return QualificationStatus.FAILED
        return QualificationStatus.QUALIFIED_LOCAL

    @staticmethod
    def _spec(
        operation_id: str,
        request_model: str,
        modes: tuple[CorpusMode, ...],
    ) -> HandlerSpec:
        return HandlerSpec(
            operation_id=operation_id,
            handler_id=f"p3.s35.{operation_id}",
            request_model=request_model,
            supported_modes=modes,
        )

    @staticmethod
    def _qualification(
        operation_id: str,
        mode: CorpusMode,
        status: QualificationStatus,
        reasons: Iterable[str],
    ) -> OperationModeQualification:
        return OperationModeQualification(
            operation_id=operation_id,
            mode_id=mode,
            status=status,
            reason_codes=tuple(reasons),
            required_capabilities=("keyword_retrieval", "available_at_filtering"),
            test_targets=(
                "tests/unit/test_handlers.py",
                "tests/property/test_point_in_time_properties.py",
            ),
        )

    @staticmethod
    def _manifest(
        snapshot: CorpusIndexSnapshot,
        suffix: str,
        specs: tuple[HandlerSpec, ...],
    ) -> HandlerBundleManifest:
        base = {
            "bundle_id": f"corpus_{suffix}_{snapshot.content_hash[:20]}",
            "handlers": specs,
        }
        return HandlerBundleManifest(content_hash=content_hash(base), **base)

    @staticmethod
    def _panel(
        snapshot: CorpusIndexSnapshot,
        records: Iterable[OperationModeQualification],
    ) -> CorpusOperationQualificationPanel:
        ordered = tuple(
            sorted(records, key=lambda item: (item.operation_id, item.mode_id.value))
        )
        base = {"snapshot_id": snapshot.snapshot_id, "records": ordered}
        return CorpusOperationQualificationPanel(content_hash=content_hash(base), **base)
