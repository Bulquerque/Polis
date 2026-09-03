from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from quant_pipeline.phase_09.contracts.integrity import (
    payload_sha256,
    sha256_bytes,
    verify_integrity,
)
from quant_pipeline.phase_09.contracts.lineage import (
    LineageGap,
    LineageGapReport,
    LineageManifest,
    LineageRelation,
    LineageResolutionReceipt,
    LineageResolutionStatus,
    ResolvedLineageGraph,
)
from quant_pipeline.phase_09.contracts.validation import ValidatedP8EvaluationHandoff

from .ports import ArtifactStoreError, ArtifactStoreReadPort


@dataclass(frozen=True, slots=True)
class LineageResolutionPolicy:
    required_phase_ids: tuple[str, ...] = ("P2", "P4", "P5", "P6", "P7", "P8")
    verify_all_artifact_hashes: bool = True
    allow_nonmaterial_gaps: bool = True


@dataclass(frozen=True, slots=True)
class LineageResolutionOutcome:
    graph: ResolvedLineageGraph | None
    gap_report: LineageGapReport
    receipt: LineageResolutionReceipt | None


class ImmutableLineageChainResolver:
    module_id = "P9.S1.M02"

    def __init__(self, artifact_store: ArtifactStoreReadPort) -> None:
        self._artifact_store = artifact_store

    def resolve(
        self,
        validated: ValidatedP8EvaluationHandoff,
        policy: LineageResolutionPolicy,
    ) -> LineageResolutionOutcome:
        manifest_ref = next(
            (
                ref
                for ref in validated.accepted_artifacts
                if ref.artifact_type == "lineage_manifest" or ref.schema_name == "lineage_manifest"
            ),
            None,
        )
        if manifest_ref is None:
            gap = LineageGap(
                gap_id="missing-lineage-manifest",
                description="handoff does not contain an accepted lineage manifest",
                material=True,
                reason_code="P9_S1_LINEAGE_PARENT_MISSING",
            )
            report = LineageGapReport(
                status=LineageResolutionStatus.UNAVAILABLE,
                gaps=(gap,),
                required_phase_ids=policy.required_phase_ids,
                observed_phase_ids=(),
            )
            return LineageResolutionOutcome(graph=None, gap_report=report, receipt=None)

        try:
            raw = self._artifact_store.read_bytes(manifest_ref.location)
            if sha256_bytes(raw) != manifest_ref.content_sha256:
                raise ValueError("lineage manifest content hash mismatch")
            manifest = LineageManifest.model_validate_json(raw)
        except (ArtifactStoreError, ValidationError, ValueError) as exc:
            gap = LineageGap(
                gap_id="corrupt-lineage-manifest",
                description=f"lineage manifest cannot be validated: {exc}",
                material=True,
                reason_code="P9_S1_LINEAGE_HASH_MISMATCH",
                affected_node_ids=(),
            )
            report = LineageGapReport(
                status=LineageResolutionStatus.CORRUPT,
                gaps=(gap,),
                required_phase_ids=policy.required_phase_ids,
                observed_phase_ids=(),
            )
            return LineageResolutionOutcome(graph=None, gap_report=report, receipt=None)

        if not verify_integrity(manifest.payload, manifest.integrity):
            gap = LineageGap(
                gap_id="lineage-envelope-mismatch",
                description="lineage manifest payload hash does not match its integrity envelope",
                material=True,
                reason_code="P9_S1_LINEAGE_HASH_MISMATCH",
            )
            report = LineageGapReport(
                status=LineageResolutionStatus.CORRUPT,
                gaps=(gap,),
                required_phase_ids=policy.required_phase_ids,
                observed_phase_ids=(),
            )
            return LineageResolutionOutcome(graph=None, gap_report=report, receipt=None)

        nodes = {node.node_id: node for node in manifest.payload.nodes}
        observed_phases = tuple(sorted({node.phase_id for node in nodes.values()}))
        gaps: list[LineageGap] = []

        for required_phase in policy.required_phase_ids:
            if required_phase not in observed_phases:
                gaps.append(
                    LineageGap(
                        gap_id=f"missing-phase-{required_phase}",
                        description=f"required lineage phase {required_phase} is absent",
                        material=True,
                        reason_code="P9_S1_LINEAGE_PARENT_MISSING",
                    )
                )

        if any(node.artifact.cycle_id != validated.handoff.cycle_id for node in nodes.values()):
            affected = tuple(
                sorted(
                    node.node_id
                    for node in nodes.values()
                    if node.artifact.cycle_id != validated.handoff.cycle_id
                )
            )
            gaps.append(
                LineageGap(
                    gap_id="cross-cycle-lineage",
                    description="lineage contains artifacts from a different cycle",
                    material=True,
                    reason_code="P9_S1_LINEAGE_VERSION_AMBIGUOUS",
                    affected_node_ids=affected,
                )
            )

        verified_artifacts: list[str] = []
        unresolved_artifacts: list[str] = []
        if policy.verify_all_artifact_hashes:
            for node in nodes.values():
                try:
                    content = self._artifact_store.read_bytes(node.artifact.location)
                except ArtifactStoreError:
                    unresolved_artifacts.append(node.artifact.artifact_id)
                    gaps.append(
                        LineageGap(
                            gap_id=f"missing-artifact-{node.node_id}",
                            description="lineage artifact bytes are unavailable",
                            material=True,
                            reason_code="P9_S1_LINEAGE_PARENT_MISSING",
                            affected_node_ids=(node.node_id,),
                        )
                    )
                    continue
                if sha256_bytes(content) != node.artifact.content_sha256:
                    unresolved_artifacts.append(node.artifact.artifact_id)
                    gaps.append(
                        LineageGap(
                            gap_id=f"hash-mismatch-{node.node_id}",
                            description="lineage artifact bytes do not match the recorded hash",
                            material=True,
                            reason_code="P9_S1_LINEAGE_HASH_MISMATCH",
                            affected_node_ids=(node.node_id,),
                        )
                    )
                else:
                    verified_artifacts.append(node.artifact.artifact_id)

        try:
            order = self._topological_order(manifest)
        except ValueError:
            gaps.append(
                LineageGap(
                    gap_id="lineage-cycle",
                    description="DERIVED_FROM lineage contains a cycle",
                    material=True,
                    reason_code="P9_S1_LINEAGE_CYCLE_DETECTED",
                    affected_node_ids=tuple(sorted(nodes)),
                )
            )
            report = LineageGapReport(
                status=LineageResolutionStatus.CORRUPT,
                gaps=tuple(gaps),
                required_phase_ids=policy.required_phase_ids,
                observed_phase_ids=observed_phases,
            )
            return LineageResolutionOutcome(graph=None, gap_report=report, receipt=None)

        material_gaps = [gap for gap in gaps if gap.material]
        if material_gaps:
            status = LineageResolutionStatus.INCOMPLETE_MATERIAL
        elif gaps:
            status = LineageResolutionStatus.RESOLVED_WITH_NONMATERIAL_GAPS
        else:
            status = LineageResolutionStatus.RESOLVED_COMPLETE

        graph_payload = {
            "nodes": manifest.payload.nodes,
            "edges": manifest.payload.edges,
            "topological_order": order,
            "gaps": gaps,
        }
        graph_hash = payload_sha256(graph_payload)
        graph = ResolvedLineageGraph(
            status=status,
            nodes=manifest.payload.nodes,
            edges=manifest.payload.edges,
            topological_order=order,
            gaps=tuple(gaps),
            graph_sha256=graph_hash,
        )
        report = LineageGapReport(
            status=status,
            gaps=tuple(gaps),
            required_phase_ids=policy.required_phase_ids,
            observed_phase_ids=observed_phases,
        )
        receipt = LineageResolutionReceipt(
            manifest_artifact_id=manifest_ref.artifact_id,
            graph_sha256=graph_hash,
            verified_artifact_ids=tuple(sorted(verified_artifacts)),
            unresolved_artifact_ids=tuple(sorted(unresolved_artifacts)),
            reason_codes=tuple(sorted({gap.reason_code for gap in gaps})),
        )
        return LineageResolutionOutcome(graph=graph, gap_report=report, receipt=receipt)

    @staticmethod
    def _topological_order(manifest: LineageManifest) -> tuple[str, ...]:
        node_ids = {node.node_id for node in manifest.payload.nodes}
        children: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
        indegree: dict[str, int] = {node_id: 0 for node_id in node_ids}
        for edge in manifest.payload.edges:
            if edge.relation is not LineageRelation.DERIVED_FROM:
                continue
            children[edge.parent_node_id].add(edge.child_node_id)
            indegree[edge.child_node_id] += 1
        ready = sorted(node_id for node_id, degree in indegree.items() if degree == 0)
        order: list[str] = []
        while ready:
            current = ready.pop(0)
            order.append(current)
            for child in sorted(children[current]):
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(child)
                    ready.sort()
        if len(order) != len(node_ids):
            raise ValueError("lineage cycle detected")
        return tuple(order)
