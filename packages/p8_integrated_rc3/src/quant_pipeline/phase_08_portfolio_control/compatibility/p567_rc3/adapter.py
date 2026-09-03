"""Strict P5/P6/P7 RC3 → native P8 contract adapter.

Design rules
------------
* P5 source objects are authenticated against their native P5 hash semantics,
  their P5→P6 manifest references, and the enclosing handoff hash before wrapping.
* P6/P7 source objects remain immutable evidence and are wrapped using P8 raw
  content hashes; their reported hashes are retained in the adaptation receipt.
* P7 score values are deliberately down-cast to ORDINAL preferences. No RC3
  score is interpreted as expected return or portfolio weight.
* P6 liquidity scores are not converted to capacity units. The native P8
  liquidity component remains UNAVAILABLE until a true capacity is supplied.
* P6 option lifecycle is UNAVAILABLE when RC3 reports exercise/assignment as
  NOT_MODELLED. This preserves candidates but prevents unsafe execution.
* All transformed artifacts are native, strict P8 models and can be consumed by
  the unmodified S1/S2 implementation.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from quant_pipeline.phase_08_contracts.canonical import (
    canonical_json_bytes,
    canonical_sha256,
    finalize_content_hash,
    raw_sha256,
)
from quant_pipeline.phase_08_contracts.common import ArtifactReference
from quant_pipeline.phase_08_contracts.enums import (
    ComponentQualificationStatus,
    ConfidenceState,
    ExerciseStyle,
    HorizonUnit,
    P7TerminalState,
    PositionSide,
    ProbabilityMeasure,
    ScoreSemantics,
    SettlementType,
)
from quant_pipeline.phase_08_contracts.p5 import HorizonSpec, P5BeliefEvidenceBundleV1
from quant_pipeline.phase_08_contracts.p6 import CandidateLegV1, P6CandidateEconomicPackageV1, UnitEconomicsV1
from quant_pipeline.phase_08_contracts.p7 import (
    ComparisonGroupRecord,
    P7RankingHandoffV1,
    P7TerminalCandidateRecord,
    RankedCandidateRecord,
)
from quant_pipeline.phase_08_portfolio_control.scenario_engineering.contracts import (
    ArtifactRef as S3ArtifactRef,
    BeliefRecord,
    DistributionType,
    EmpiricalPayload,
    HorizonSpec as S3HorizonSpec,
    HorizonUnit as S3HorizonUnit,
    ProbabilityMeasure as S3ProbabilityMeasure,
)

from .models import (
    P567RC3AdaptationReceiptV1,
    P567RC3AdaptationResult,
    SourceArtifactAuditRecord,
)

ADAPTER_ID = "P8.P567_RC3.BRIDGE"
ADAPTER_RELEASE = "0.3.0rc3"


class P567RC3CompatibilityError(ValueError):
    """Fail-closed validation error for incompatible or incomplete RC3 input."""


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P567RC3CompatibilityError(f"{label} must be an object")
    if not all(isinstance(key, str) for key in value):
        raise P567RC3CompatibilityError(f"{label} keys must be strings")
    return cast(Mapping[str, Any], value)


def _sequence(value: object, label: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise P567RC3CompatibilityError(f"{label} must be an array")
    return cast(Sequence[Any], value)


def _required(mapping: Mapping[str, Any], key: str, label: str) -> Any:
    if key not in mapping:
        raise P567RC3CompatibilityError(f"{label} missing required field: {key}")
    return mapping[key]


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise P567RC3CompatibilityError(f"{label} must be a non-empty string")
    return value


def _decimal(value: object, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise P567RC3CompatibilityError(f"{label} must be a decimal value")
    try:
        return Decimal(str(value))
    except (ValueError, InvalidOperation) as exc:  # exact boundary conversion
        raise P567RC3CompatibilityError(f"{label} is not a decimal value") from exc


def _dt(value: object, label: str) -> datetime:
    text = _text(value, label).replace("Z", "+00:00")
    try:
        result = datetime.fromisoformat(text)
    except ValueError as exc:
        raise P567RC3CompatibilityError(f"{label} is not ISO-8601") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise P567RC3CompatibilityError(f"{label} must be timezone-aware")
    return result.astimezone(UTC)


def _optional_dt(value: object, label: str) -> datetime | None:
    return None if value is None else _dt(value, label)


def _records(panel: Mapping[str, Any], label: str) -> tuple[Mapping[str, Any], ...]:
    rows = _sequence(panel.get("records", ()), f"{label}.records")
    return tuple(_mapping(row, f"{label}.records[{index}]") for index, row in enumerate(rows))


def _get_path(root: Mapping[str, Any], path: str) -> Mapping[str, Any] | None:
    current: object = root
    for key in path.split("."):
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return _mapping(current, path)


def _first_path(root: Mapping[str, Any], paths: Iterable[str], *, required: bool, label: str) -> Mapping[str, Any] | None:
    for path in paths:
        found = _get_path(root, path)
        if found is not None:
            return found
    if required:
        raise P567RC3CompatibilityError(f"unable to locate RC3 artifact: {label}")
    return None


def _reported_hash(source: Mapping[str, Any]) -> tuple[str | None, str | None]:
    for field in ("content_sha256", "artifact_sha256", "artifact_hash", "content_hash"):
        value = source.get(field)
        if isinstance(value, str) and value:
            return value, field
    return None, None


def _safe_token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "artifact"


def _p5_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _p5_stable_hash(*values: object) -> str:
    return _p5_sha256(values)


def _p5_payload_for_hash(source: Mapping[str, Any], label: str) -> Mapping[str, Any]:
    if isinstance(source.get("content"), Mapping) and isinstance(source.get("artifact_type"), str):
        return {"artifact_type": source["artifact_type"], "content": source["content"]}
    if isinstance(source.get("records"), Sequence) and not isinstance(source.get("records"), (str, bytes, bytearray)):
        return {"records": source["records"]}
    if source.get("availability") == "UNAVAILABLE" and isinstance(source.get("artifact_type"), str):
        return {
            "artifact_type": source["artifact_type"],
            "availability": "UNAVAILABLE",
            "reason_code": source.get("reason_code"),
        }
    raise P567RC3CompatibilityError(f"{label} has no supported P5 native hash payload")


def _validate_p5_manifest_hash(manifest: Mapping[str, Any]) -> None:
    reported = _text(manifest.get("content_sha256"), "P5 output manifest.content_sha256")
    scope = _text(manifest.get("hash_scope"), "P5 output manifest.hash_scope")
    if scope != "FULL_MANIFEST_EXCLUDING_CONTENT_SHA256":
        raise P567RC3CompatibilityError(f"unsupported P5 output manifest hash scope: {scope}")
    observed = _p5_sha256({key: value for key, value in manifest.items() if key != "content_sha256"})
    if observed != reported:
        raise P567RC3CompatibilityError("P5 output handoff manifest content_sha256 mismatch")


def _validate_p5_strategy_manifest(manifest: Mapping[str, Any]) -> None:
    reference_names = (
        "market_belief_state", "return_distributions", "volatility_distributions",
        "path_risk_forecasts", "scenario_paths", "ambiguity_sets", "dependence_states",
        "regime_ood_states", "forecast_confidence", "availability_report", "lineage_report",
    )
    capability_names = (
        "scenario_capability", "surface_capability", "ambiguity_capability",
        "extended_scenario_path_capability", "extended_ambiguity_capability",
        "producer_contract_version", "handoff_mode", "published_artifacts", "published_capabilities",
    )
    payload = {
        "references": {name: _mapping(_required(manifest, name, "P5 strategy manifest"), f"P5 reference {name}") for name in reference_names},
        **{name: _required(manifest, name, "P5 strategy manifest") for name in capability_names},
    }
    observed = _p5_stable_hash(
        _text(manifest.get("producer_module_id"), "P5 strategy manifest.producer_module_id"),
        _text(manifest.get("schema_version"), "P5 strategy manifest.schema_version"),
        payload,
    )
    reported = _text(manifest.get("artifact_sha256"), "P5 strategy manifest.artifact_sha256")
    if observed != reported:
        raise P567RC3CompatibilityError("P5 strategy manifest artifact_sha256 mismatch")


def _validate_p5_embedded_artifacts(
    embedded: Mapping[str, Any], strategy_manifest: Mapping[str, Any]
) -> None:
    published = _sequence(strategy_manifest.get("published_artifacts", ()), "P5 strategy manifest.published_artifacts")
    if set(map(str, published)) != set(embedded):
        raise P567RC3CompatibilityError("P5 published_artifacts does not match embedded_v2_artifacts")
    for name, raw_source in embedded.items():
        source = _mapping(raw_source, f"P5 embedded artifact {name}")
        reference = _mapping(_required(strategy_manifest, name, "P5 strategy manifest"), f"P5 reference {name}")
        expected_identity = {
            "artifact_id": source.get("artifact_id"),
            "content_hash": source.get("artifact_sha256"),
            "schema_version": source.get("schema_version"),
        }
        for field, expected in expected_identity.items():
            if str(reference.get(field)) != str(expected):
                raise P567RC3CompatibilityError(f"P5 reference mismatch for {name}.{field}")
        records = source.get("records")
        if reference.get("row_count") is not None and isinstance(records, Sequence) and not isinstance(records, (str, bytes, bytearray)):
            if int(reference["row_count"]) != len(records):
                raise P567RC3CompatibilityError(f"P5 row_count mismatch for {name}")
        payload = _p5_payload_for_hash(source, f"P5 embedded artifact {name}")
        observed = _p5_stable_hash(
            _text(source.get("producer_module_id"), f"P5 {name}.producer_module_id"),
            _text(source.get("schema_version"), f"P5 {name}.schema_version"),
            payload,
        )
        reported = _text(source.get("artifact_sha256"), f"P5 {name}.artifact_sha256")
        if observed != reported:
            raise P567RC3CompatibilityError(f"P5 embedded artifact hash mismatch: {name}")
        content_sha = source.get("content_sha256")
        if content_sha is not None:
            content_records = source.get("records")
            if not isinstance(content_records, Sequence) or isinstance(content_records, (str, bytes, bytearray)):
                raise P567RC3CompatibilityError(f"P5 {name}.content_sha256 lacks records")
            if _p5_sha256(content_records) != str(content_sha):
                raise P567RC3CompatibilityError(f"P5 embedded content_sha256 mismatch: {name}")


class _ArtifactBuilder:
    def __init__(self, *, source_releases: Mapping[str, str]) -> None:
        self.artifacts: dict[str, bytes] = {}
        self.audit_records: list[SourceArtifactAuditRecord] = []
        self.source_releases = dict(source_releases)

    def source(
        self,
        *,
        phase: str,
        source_type: str,
        source: Mapping[str, Any],
        relationship_type: str = "SOURCE_EVIDENCE",
        available_at: datetime | None = None,
    ) -> ArtifactReference:
        source_id = str(source.get("artifact_id") or source.get("artifact_name") or source_type)
        source_schema = str(source.get("schema_version") or "RC3_UNVERSIONED")
        source_available = available_at or _dt(
            source.get("available_at") or source.get("created_at") or source.get("decision_time"),
            f"{phase}.{source_type}.available_at",
        )
        reported_hash, hash_field = _reported_hash(source)
        wrapper = {
            "contract_version": "P567_RC3_SOURCE_WRAPPER_V1",
            "schema_version": "1.0.0",
            "source_phase": phase,
            "source_release": self.source_releases[phase],
            "source_artifact_id": source_id,
            "source_artifact_type": source_type,
            "source_schema_version": source_schema,
            "source_reported_hash": reported_hash,
            "source_hash_field": hash_field,
            "source_payload": source,
        }
        raw = canonical_json_bytes(wrapper)
        digest = raw_sha256(raw)
        artifact_id = f"p567rc3-{phase.lower()}-{_safe_token(source_type.lower())}-{digest[:20]}"
        reference = ArtifactReference(
            artifact_id=artifact_id,
            artifact_type=f"{phase}_RC3_{source_type.upper()}_SOURCE",
            schema_version="1.0.0",
            contract_version="P567_RC3_SOURCE_WRAPPER_V1",
            content_sha256=digest,
            available_at=source_available,
            relationship_type=relationship_type,
        )
        prior = self.artifacts.get(artifact_id)
        if prior is not None and prior != raw:
            raise P567RC3CompatibilityError(f"source artifact ID collision: {artifact_id}")
        self.artifacts[artifact_id] = raw
        self.audit_records.append(
            SourceArtifactAuditRecord(
                source_phase=cast(Any, phase),
                source_release=self.source_releases[phase],
                source_artifact_id=source_id,
                source_artifact_type=source_type,
                source_schema_version=source_schema,
                source_reported_hash=reported_hash,
                source_hash_field=hash_field,
                wrapped_reference=reference,
            )
        )
        return reference

    def native(
        self,
        *,
        artifact_id: str,
        artifact_type: str,
        contract_version: str,
        schema_version: str,
        model: object,
        available_at: datetime,
        relationship_type: str | None = None,
    ) -> ArtifactReference:
        raw = canonical_json_bytes(model)
        digest = raw_sha256(raw)
        reference = ArtifactReference(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            schema_version=schema_version,
            contract_version=contract_version,
            content_sha256=digest,
            available_at=available_at,
            relationship_type=relationship_type,
        )
        prior = self.artifacts.get(artifact_id)
        if prior is not None and prior != raw:
            raise P567RC3CompatibilityError(f"native artifact ID collision: {artifact_id}")
        self.artifacts[artifact_id] = raw
        return reference


class P567RC3Adapter:
    """Translate a complete RC3 chain publication into native P8 inputs."""

    def adapt(
        self,
        *,
        p5_publication: Mapping[str, object],
        p6_outputs: Mapping[str, object],
        p7_result: Mapping[str, object],
        p8_run_id: str,
        p8_cycle_id: str,
        p8_decision_time: datetime,
        market_cutoff_at: datetime,
        computed_at: datetime,
        recorded_at: datetime,
        available_at: datetime,
    ) -> P567RC3AdaptationResult:
        p5 = _mapping(p5_publication, "p5_publication")
        p6 = _mapping(p6_outputs, "p6_outputs")
        p7 = _mapping(p7_result, "p7_result")
        p8_decision_time = p8_decision_time.astimezone(UTC)
        market_cutoff_at = market_cutoff_at.astimezone(UTC)
        computed_at = computed_at.astimezone(UTC)
        recorded_at = recorded_at.astimezone(UTC)
        available_at = available_at.astimezone(UTC)
        p7_source_decision = self._source_p7_decision(p7)
        if not (market_cutoff_at <= p7_source_decision <= computed_at <= recorded_at <= available_at <= p8_decision_time):
            raise P567RC3CompatibilityError(
                "bridge clocks must satisfy market_cutoff <= P7 decision <= computed <= recorded <= "
                "available <= P8 consumer decision"
            )

        p5_manifest = _mapping(_required(p5, "phase5_output_handoff_manifest", "p5_publication"), "P5 manifest")
        p5_embedded = _mapping(_required(p5_manifest, "embedded_v2_artifacts", "P5 manifest"), "P5 embedded artifacts")
        p5_strategy_manifest = _mapping(
            _required(p5, "phase6_strategy_scenario_manifest", "p5_publication"),
            "P5 strategy manifest",
        )
        p5_release = _text(_required(p5_manifest, "pipeline_version", "P5 manifest"), "P5 release")
        _validate_p5_manifest_hash(p5_manifest)
        _validate_p5_strategy_manifest(p5_strategy_manifest)
        if str(p5_manifest.get("phase6_strategy_scenario_manifest_id")) != str(p5_strategy_manifest.get("artifact_id")):
            raise P567RC3CompatibilityError("P5 output manifest does not bind the supplied strategy manifest")
        _validate_p5_embedded_artifacts(p5_embedded, p5_strategy_manifest)
        p6_release = self._p6_release(p6)
        p7_release = self._p7_release(p7)
        builder = _ArtifactBuilder(source_releases={"P5": p5_release, "P6": p6_release, "P7": p7_release})

        p5_source_refs = self._wrap_p5_sources(p5_embedded, builder)
        p6_source_refs = self._wrap_p6_sources(p6, builder)
        p7_source_refs = self._wrap_p7_sources(p7, builder)

        p5_bundles, p5_bundle_refs, s3_beliefs = self._build_p5_bundles(
            p5_embedded=p5_embedded,
            source_refs=p5_source_refs,
            builder=builder,
        )
        p6_packages, p6_package_refs = self._build_p6_packages(
            p6=p6,
            p5_bundle_refs=p5_bundle_refs,
            p6_source_refs=p6_source_refs,
            builder=builder,
            p8_decision_time=p8_decision_time,
        )
        populations = self._extract_p7_populations(p7=p7, p6=p6)
        groups = self._build_comparison_groups(p7=p7, p6=p6, populations=populations)

        receipt = self._build_receipt(
            builder=builder,
            p8_run_id=p8_run_id,
            p8_cycle_id=p8_cycle_id,
            p8_decision_time=p8_decision_time,
            computed_at=computed_at,
            p5_release=p5_release,
            p6_release=p6_release,
            p7_release=p7_release,
            populations=populations,
        )
        receipt_id = f"p567rc3-adaptation-{receipt.content_sha256[:24]}"
        receipt_ref = builder.native(
            artifact_id=receipt_id,
            artifact_type="P567_RC3_TO_P8_ADAPTATION_RECEIPT_V1",
            contract_version=receipt.contract_version,
            schema_version=receipt.schema_version,
            model=receipt,
            available_at=available_at,
            relationship_type="ADAPTATION_PROOF",
        )

        handoff = self._build_handoff(
            populations=populations,
            groups=groups,
            p6_refs=p6_package_refs,
            p7_source_refs=p7_source_refs,
            receipt_ref=receipt_ref,
            p8_run_id=p8_run_id,
            p8_cycle_id=p8_cycle_id,
            p7_decision_time=p7_source_decision,
            market_cutoff_at=market_cutoff_at,
            computed_at=computed_at,
            recorded_at=recorded_at,
            available_at=available_at,
            p7_release=p7_release,
        )
        handoff_bytes = canonical_json_bytes(handoff)
        return P567RC3AdaptationResult(
            handoff=handoff,
            handoff_bytes=handoff_bytes,
            p5_bundles=p5_bundles,
            p6_packages=p6_packages,
            s3_beliefs=s3_beliefs,
            artifact_bytes=dict(builder.artifacts),
            adaptation_receipt=receipt,
            adaptation_receipt_ref=receipt_ref,
        )

    @staticmethod
    def _source_p7_decision(p7: Mapping[str, Any]) -> datetime:
        panel = _first_path(
            p7,
            (
                "foundation.comparison.outputs.candidate_comparison_group_panel",
                "finalization.s7.abstained_candidate_panel",
                "finalization.s8.ranked_strategy_candidate_panel",
                "outputs.candidate_comparison_group_panel",
            ),
            required=True,
            label="P7 source decision",
        )
        assert panel is not None
        raw = panel.get("decision_time")
        if raw is None:
            rows = _records(panel, "P7 source decision")
            if not rows:
                raise P567RC3CompatibilityError("P7 source decision cannot be resolved")
            raw = rows[0].get("decision_time")
        return _dt(raw, "P7 source decision_time")

    @staticmethod
    def _p6_release(p6: Mapping[str, Any]) -> str:
        panel = _mapping(_required(p6, "canonical_strategy_candidate_panel", "p6_outputs"), "P6 candidates")
        return str(panel.get("schema_version") or "6.2.0-rc2")

    @staticmethod
    def _p7_release(p7: Mapping[str, Any]) -> str:
        receipt = _first_path(
            p7,
            ("release.outputs.p7_phase_release_receipt", "p7_phase_release_receipt"),
            required=False,
            label="P7 release receipt",
        )
        if receipt is not None:
            rows = _records(receipt, "P7 release receipt")
            if rows:
                row = rows[0]
                for key in ("phase_version", "release_version", "pipeline_version"):
                    value = row.get(key)
                    if isinstance(value, str) and value:
                        return value
        return "2.3.1rc3"

    @staticmethod
    def _wrap_p5_sources(p5_embedded: Mapping[str, Any], builder: _ArtifactBuilder) -> dict[str, ArtifactReference]:
        refs: dict[str, ArtifactReference] = {}
        for name, raw in sorted(p5_embedded.items()):
            source = _mapping(raw, f"P5 embedded {name}")
            refs[name] = builder.source(phase="P5", source_type=name, source=source)
        return refs

    @staticmethod
    def _wrap_p6_sources(p6: Mapping[str, Any], builder: _ArtifactBuilder) -> dict[str, ArtifactReference]:
        names = (
            "canonical_strategy_candidate_panel",
            "strategy_leg_panel",
            "strategy_payoff_panel",
            "strategy_risk_panel",
            "strategy_greek_panel",
            "strategy_cost_liquidity_panel",
            "strategy_qualification_panel",
            "strategy_scenario_evaluation_panel",
            "strategy_lineage_panel",
            "validated_option_contract_panel",
            "validated_underlying_panel",
            "validated_market_belief_state",
            "candidate_equivalence_panel_final",
            "phase7_strategy_handoff_manifest",
        )
        refs: dict[str, ArtifactReference] = {}
        for name in names:
            raw = p6.get(name)
            if raw is None:
                continue
            refs[name] = builder.source(phase="P6", source_type=name, source=_mapping(raw, f"P6 {name}"))
        return refs

    @staticmethod
    def _wrap_p7_sources(p7: Mapping[str, Any], builder: _ArtifactBuilder) -> dict[str, ArtifactReference]:
        paths = {
            "phase8_strategy_ranking_handoff_manifest": (
                "finalization.s8.phase8_strategy_ranking_handoff_manifest",
                "outputs.phase8_strategy_ranking_handoff_manifest",
                "phase8_strategy_ranking_handoff_manifest",
            ),
            "ranked_strategy_candidate_panel": (
                "finalization.s8.ranked_strategy_candidate_panel",
                "outputs.ranked_strategy_candidate_panel",
                "ranked_strategy_candidate_panel",
            ),
            "ranking_trace_panel": (
                "finalization.s8.ranking_trace_panel",
                "outputs.ranking_trace_panel",
                "ranking_trace_panel",
            ),
            "strategy_thesis_card_panel": (
                "finalization.s8.strategy_thesis_card_panel",
                "outputs.strategy_thesis_card_panel",
                "strategy_thesis_card_panel",
            ),
            "score_decomposition_panel": (
                "tournament.outputs.score_decomposition_panel",
                "outputs.score_decomposition_panel",
                "score_decomposition_panel",
            ),
            "abstained_candidate_panel": (
                "finalization.s7.abstained_candidate_panel",
                "outputs.abstained_candidate_panel",
                "abstained_candidate_panel",
            ),
            "safety_blocked_candidate_panel": (
                "finalization.s7.safety_blocked_candidate_panel",
                "outputs.safety_blocked_candidate_panel",
                "safety_blocked_candidate_panel",
            ),
            "final_blocked_candidate_panel": (
                "finalization.s7.final_blocked_candidate_panel",
                "outputs.final_blocked_candidate_panel",
                "final_blocked_candidate_panel",
            ),
            "eligibility_blocked_candidate_panel": (
                "foundation.comparison.outputs.eligibility_blocked_candidate_panel",
                "eligibility_blocked_candidate_panel",
            ),
            "candidate_comparison_group_panel": (
                "foundation.comparison.outputs.candidate_comparison_group_panel",
                "candidate_comparison_group_panel",
            ),
            "rankability_group_report": (
                "finalization.s7.rankability_group_report",
                "outputs.rankability_group_report",
                "rankability_group_report",
            ),
            "ranking_group_summary_panel": (
                "finalization.s8.ranking_group_summary_panel",
                "outputs.ranking_group_summary_panel",
                "ranking_group_summary_panel",
            ),
            "p7_phase_release_receipt": (
                "release.outputs.p7_phase_release_receipt",
                "p7_phase_release_receipt",
            ),
        }
        refs: dict[str, ArtifactReference] = {}
        for name, candidates in paths.items():
            source = _first_path(p7, candidates, required=False, label=name)
            if source is not None:
                refs[name] = builder.source(phase="P7", source_type=name, source=source)
        return refs

    @staticmethod
    def _artifact_rows(source: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
        rows = source.get("records")
        if rows is None and isinstance(source.get("content"), Mapping):
            rows = cast(Mapping[str, Any], source["content"]).get("records")
        return _records({"records": rows or ()}, "source artifact")

    def _build_p5_bundles(
        self,
        *,
        p5_embedded: Mapping[str, Any],
        source_refs: Mapping[str, ArtifactReference],
        builder: _ArtifactBuilder,
    ) -> tuple[dict[str, P5BeliefEvidenceBundleV1], dict[str, ArtifactReference], dict[str, BeliefRecord]]:
        market = _mapping(_required(p5_embedded, "market_belief_state", "P5 embedded"), "P5 market belief")
        returns = _mapping(_required(p5_embedded, "return_distributions", "P5 embedded"), "P5 returns")
        confidence = _mapping(_required(p5_embedded, "forecast_confidence", "P5 embedded"), "P5 confidence")
        regime = _mapping(_required(p5_embedded, "regime_ood_states", "P5 embedded"), "P5 regime/OOD")
        market_by_underlying = {str(row["underlying_id"]): row for row in self._artifact_rows(market)}
        return_by_underlying = {str(row["underlying"]): row for row in self._artifact_rows(returns)}
        confidence_by_underlying = {str(row["underlying"]): row for row in self._artifact_rows(confidence)}
        regime_by_underlying: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in self._artifact_rows(regime):
            regime_by_underlying[str(row["underlying"])].append(row)

        bundles: dict[str, P5BeliefEvidenceBundleV1] = {}
        refs: dict[str, ArtifactReference] = {}
        beliefs: dict[str, BeliefRecord] = {}
        for underlying in sorted(market_by_underlying):
            market_row = market_by_underlying[underlying]
            return_row = return_by_underlying.get(underlying)
            if return_row is None:
                raise P567RC3CompatibilityError(f"P5 return distribution missing for {underlying}")
            confidence_row = confidence_by_underlying.get(underlying)
            horizon_days = int(market_row.get("horizon_days") or self._parse_horizon_days(return_row.get("horizon")))
            source_decision = _dt(market_row["decision_time"], f"P5 market belief {underlying}.decision_time")
            optional = source_refs
            bundle = P5BeliefEvidenceBundleV1(
                belief_state_id=_text(market_row.get("belief_state_id"), f"P5 belief {underlying}.belief_state_id"),
                target_id=str((confidence_row or return_row).get("target_id") or "excess_return"),
                underlying_or_factor_id=underlying,
                forecast_horizon=HorizonSpec(value=horizon_days, unit=HorizonUnit.CALENDAR_DAYS),
                as_of_time=source_decision,
                decision_time=source_decision,
                resolver_id=str(market_row.get("source_artifact_id") or market.get("artifact_id") or "P5.RC3"),
                model_artifact_id=str(returns.get("artifact_id") or "P5.RC3.RETURN_DISTRIBUTIONS"),
                probability_measure=ProbabilityMeasure.PHYSICAL,
                forecast_distribution_ref=optional["return_distributions"],
                scenario_set_ref=optional.get("scenario_paths"),
                path_scenario_ref=optional.get("scenario_paths"),
                covariance_dependence_ref=optional.get("dependence_states"),
                regime_state_ref=optional.get("regime_ood_states"),
                ood_state_ref=optional.get("regime_ood_states"),
                disagreement_ref=optional.get("forecast_confidence"),
                calibration_ref=optional.get("forecast_confidence"),
                ambiguity_evidence_ref=optional.get("ambiguity_sets"),
                lineage_refs=tuple(
                    reference
                    for name, reference in sorted(optional.items())
                    if name in {"market_belief_state", "availability_report", "lineage_report"}
                ),
            )
            artifact_id = f"p5-belief-bundle-{_safe_token(underlying.lower())}-{canonical_sha256(bundle)[:18]}"
            ref = builder.native(
                artifact_id=artifact_id,
                artifact_type="P5_BELIEF_EVIDENCE_REFERENCE_BUNDLE_V1",
                contract_version="P5_BELIEF_EVIDENCE_REFERENCE_BUNDLE_V1",
                schema_version="1.0.0",
                model=bundle,
                available_at=source_refs["market_belief_state"].available_at,
                relationship_type="BELIEF_EVIDENCE",
            )
            bundles[underlying] = bundle
            refs[underlying] = ref
            beliefs[underlying] = self._build_s3_belief(
                underlying=underlying,
                bundle=bundle,
                bundle_ref=ref,
                return_row=return_row,
                confidence_row=confidence_row,
                regime_rows=regime_by_underlying.get(underlying, []),
            )
        return bundles, refs, beliefs

    @staticmethod
    def _parse_horizon_days(value: object) -> int:
        text = str(value or "1D").upper()
        match = re.fullmatch(r"(\d+)D", text)
        if not match:
            raise P567RC3CompatibilityError(f"unsupported RC3 horizon: {value!r}")
        return int(match.group(1))

    def _build_s3_belief(
        self,
        *,
        underlying: str,
        bundle: P5BeliefEvidenceBundleV1,
        bundle_ref: ArtifactReference,
        return_row: Mapping[str, Any],
        confidence_row: Mapping[str, Any] | None,
        regime_rows: Sequence[Mapping[str, Any]],
    ) -> BeliefRecord:
        distribution = _mapping(_required(return_row, "distribution", f"return distribution {underlying}"), "distribution")
        if str(distribution.get("kind", "")).upper() != "EMPIRICAL":
            raise P567RC3CompatibilityError(f"only RC3 empirical distributions are currently bridgeable: {underlying}")
        samples_raw = _sequence(_required(distribution, "samples", "empirical distribution"), "empirical samples")
        samples = tuple((float(value),) for value in samples_raw)
        if not samples:
            raise P567RC3CompatibilityError(f"empty P5 empirical distribution for {underlying}")
        calibration = None
        disagreement = None
        if confidence_row is not None:
            raw_calibration = confidence_row.get("calibration_component")
            raw_disagreement = confidence_row.get("ensemble_disagreement_component")
            calibration = None if raw_calibration is None else float(raw_calibration)
            disagreement = None if raw_disagreement is None else float(raw_disagreement)
        one_day_rows = [row for row in regime_rows if self._parse_horizon_days(row.get("horizon")) == bundle.forecast_horizon.value]
        ood_values: list[float] = []
        regime_id: str | None = None
        if one_day_rows:
            row = one_day_rows[0]
            for key in ("feature_ood", "market_state_ood", "dependence_ood", "model_ood"):
                value = row.get(key)
                if value is not None:
                    ood_values.append(float(value))
            probabilities = row.get("regime_probabilities")
            if isinstance(probabilities, Mapping) and probabilities:
                regime_id = max(probabilities, key=lambda key: float(probabilities[key]))
        horizon = S3HorizonSpec(value=bundle.forecast_horizon.value, unit=S3HorizonUnit.CALENDAR_DAYS)
        return BeliefRecord(
            belief_state_id=bundle.belief_state_id,
            target_id=bundle.target_id,
            factor_ids=(underlying,),
            distribution_type=DistributionType.EMPIRICAL,
            probability_measure=S3ProbabilityMeasure.PHYSICAL,
            forecast_horizon=horizon,
            holding_horizon=horizon,
            evaluation_horizon=horizon,
            payload=EmpiricalPayload(samples=samples),
            calibration_score=calibration,
            ood_score=max(ood_values) if ood_values else None,
            disagreement_score=disagreement,
            regime_id=regime_id,
            available_at=bundle.decision_time,
            decision_time=bundle.decision_time,
            source_ref=S3ArtifactRef(
                artifact_id=bundle_ref.artifact_id,
                content_sha256=bundle_ref.content_sha256,
                schema_version=bundle_ref.schema_version,
                contract_version=bundle_ref.contract_version,
            ),
        )

    def _build_p6_packages(
        self,
        *,
        p6: Mapping[str, Any],
        p5_bundle_refs: Mapping[str, ArtifactReference],
        p6_source_refs: Mapping[str, ArtifactReference],
        builder: _ArtifactBuilder,
        p8_decision_time: datetime,
    ) -> tuple[dict[str, P6CandidateEconomicPackageV1], dict[str, ArtifactReference]]:
        # P8 consumes the published candidate universe.  The canonical panel is
        # an internal P6.S9 working set and may contain representatives removed
        # by P6.S10; using it makes economics panels appear missing.
        candidates_panel = _mapping(
            _required(p6, "strategy_candidate_panel", "P6 outputs"),
            "P6 candidates",
        )
        candidates = _records(candidates_panel, "P6 candidates")
        # The published strategy panel owns the candidate universe, while the
        # canonical panel can retain richer lifecycle facts from the P6
        # construction step.  Keep the published legs for economics and use
        # the canonical row only as a conservative lifecycle witness.  This
        # prevents an option from becoming QUALIFIED merely because its final
        # projection omitted the original option leg.
        canonical_candidates = (
            self._index_by_candidate(p6, "canonical_strategy_candidate_panel")
            if "canonical_strategy_candidate_panel" in p6
            else {}
        )
        payoff_by_id = self._index_by_candidate(p6, "strategy_payoff_panel")
        cost_by_id = self._index_by_candidate(p6, "strategy_cost_liquidity_panel")
        qualification_by_id = self._index_by_candidate(p6, "strategy_qualification_panel")
        scenario_panel = _mapping(_required(p6, "strategy_scenario_evaluation_panel", "P6 outputs"), "P6 scenarios")
        scenario_ref = p6_source_refs["strategy_scenario_evaluation_panel"]
        option_contracts = {
            str(row["contract_id"]): row
            for row in _records(_mapping(p6.get("validated_option_contract_panel", {"records": []}), "option contracts"), "option contracts")
        }
        underlyings = {
            str(row["underlying_id"]): row
            for row in _records(_mapping(p6.get("validated_underlying_panel", {"records": []}), "underlyings"), "underlyings")
        }
        scenarios_by_candidate: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in _records(scenario_panel, "P6 scenarios"):
            scenarios_by_candidate[str(row["candidate_id"])].append(row)

        packages: dict[str, P6CandidateEconomicPackageV1] = {}
        refs: dict[str, ArtifactReference] = {}
        for row in candidates:
            candidate_id = _text(row.get("candidate_id"), "P6 candidate_id")
            underlying = _text(row.get("underlying_id"), f"P6 {candidate_id}.underlying_id")
            p5_ref = p5_bundle_refs.get(underlying)
            if p5_ref is None:
                raise P567RC3CompatibilityError(f"P5 bundle missing for candidate underlying: {underlying}")
            legs_source = _sequence(_required(row, "legs", f"P6 candidate {candidate_id}"), f"P6 {candidate_id}.legs")
            legs = tuple(
                self._build_leg(
                    leg=_mapping(raw_leg, f"P6 {candidate_id}.leg"),
                    option_contracts=option_contracts,
                    underlyings=underlyings,
                    builder=builder,
                    p8_decision_time=p8_decision_time,
                )
                for raw_leg in legs_source
            )
            currencies = {str(_mapping(raw_leg, "leg").get("currency")) for raw_leg in legs_source}
            if len(currencies) != 1 or "None" in currencies:
                raise P567RC3CompatibilityError(f"candidate {candidate_id} has ambiguous currency")
            payoff = payoff_by_id.get(candidate_id)
            cost = cost_by_id.get(candidate_id)
            qualification = qualification_by_id.get(candidate_id)
            if payoff is None or cost is None or qualification is None:
                raise P567RC3CompatibilityError(f"candidate {candidate_id} lacks P6 economics panels")
            entry_available = str(cost.get("status")) == "AVAILABLE" and cost.get("conservative_entry_cost") is not None
            payoff_available = str(payoff.get("payoff_status")) == "AVAILABLE"
            max_loss_proven = bool(qualification.get("maximum_loss_proven")) and payoff.get("maximum_loss") is not None
            lifecycle_row = canonical_candidates.get(candidate_id)
            lifecycle_legs = (
                _sequence(lifecycle_row.get("legs", ()), f"P6 canonical {candidate_id}.legs")
                if lifecycle_row is not None and lifecycle_row.get("legs")
                else legs_source
            )
            lifecycle_status = self._lifecycle_status(
                legs_source=lifecycle_legs,
                scenario_rows=scenarios_by_candidate[candidate_id],
            )
            economics = UnitEconomicsV1(
                entry_cost_status=(ComponentQualificationStatus.QUALIFIED if entry_available else ComponentQualificationStatus.UNAVAILABLE),
                payoff_status=(ComponentQualificationStatus.QUALIFIED if payoff_available else ComponentQualificationStatus.UNAVAILABLE),
                maximum_loss_status=(ComponentQualificationStatus.QUALIFIED if max_loss_proven else ComponentQualificationStatus.UNAVAILABLE),
                liquidity_status=ComponentQualificationStatus.UNAVAILABLE,
                lifecycle_status=lifecycle_status,
                unit_entry_cost=(_decimal(cost["conservative_entry_cost"], f"P6 {candidate_id}.entry_cost") if entry_available else None),
                unit_maximum_loss=(_decimal(payoff["maximum_loss"], f"P6 {candidate_id}.maximum_loss") if max_loss_proven else None),
                margin_per_unit=(
                    _decimal(qualification["margin_estimate"], f"P6 {candidate_id}.margin")
                    if str(qualification.get("margin_status")) == "AVAILABLE" and qualification.get("margin_estimate") is not None
                    else None
                ),
                liquidity_capacity_units=None,
                scenario_valuation_ref=scenario_ref,
            )
            lineage = tuple(
                p6_source_refs[name]
                for name in (
                    "canonical_strategy_candidate_panel",
                    "strategy_payoff_panel",
                    "strategy_risk_panel",
                    "strategy_cost_liquidity_panel",
                    "strategy_qualification_panel",
                    "strategy_lineage_panel",
                )
                if name in p6_source_refs
            )
            package = P6CandidateEconomicPackageV1(
                candidate_id=candidate_id,
                canonical_candidate_id=candidate_id,
                candidate_family=str(row.get("origin_template_id") or row.get("origin_mode") or "RC3_CANDIDATE"),
                objective_family=_text(row.get("objective_family"), f"P6 {candidate_id}.objective_family"),
                unit_definition=f"P6_RC3_STRATEGY_SCALE:{row.get('strategy_scale', '1')}",
                currency=cast(Any, next(iter(currencies))),
                lot_size=Decimal("1"),
                quantity_increment=Decimal("1"),
                legs=legs,
                unit_economics=economics,
                p5_belief_bundle_ref=p5_ref,
                lineage_refs=lineage,
            )
            raw_key = canonical_sha256(package)[:18]
            ref = builder.native(
                artifact_id=f"p6-economic-{_safe_token(candidate_id)}-{raw_key}",
                artifact_type="P6_CANDIDATE_ECONOMIC_PACKAGE_V1",
                contract_version="P6_CANDIDATE_ECONOMIC_PACKAGE_V1",
                schema_version="1.0.0",
                model=package,
                available_at=p6_source_refs["canonical_strategy_candidate_panel"].available_at,
                relationship_type="CANDIDATE_ECONOMICS",
            )
            packages[candidate_id] = package
            refs[candidate_id] = ref
        return packages, refs

    @staticmethod
    def _index_by_candidate(p6: Mapping[str, Any], name: str) -> dict[str, Mapping[str, Any]]:
        panel = _mapping(_required(p6, name, "P6 outputs"), f"P6 {name}")
        return {str(row["candidate_id"]): row for row in _records(panel, f"P6 {name}")}

    def _build_leg(
        self,
        *,
        leg: Mapping[str, Any],
        option_contracts: Mapping[str, Mapping[str, Any]],
        underlyings: Mapping[str, Mapping[str, Any]],
        builder: _ArtifactBuilder,
        p8_decision_time: datetime,
    ) -> CandidateLegV1:
        instrument_id = _text(leg.get("instrument_id"), "P6 leg.instrument_id")
        instrument_type = _text(leg.get("instrument_type"), f"P6 leg {instrument_id}.instrument_type")
        side = PositionSide.LONG if str(leg.get("side")).upper() == "LONG" else PositionSide.SHORT
        quantity = abs(_decimal(leg.get("quantity"), f"P6 leg {instrument_id}.quantity"))
        if quantity == 0:
            raise P567RC3CompatibilityError(f"P6 leg has zero quantity: {instrument_id}")
        is_option = instrument_type.upper() in {"OPTION", "CALL", "PUT"} or instrument_id in option_contracts
        if is_option:
            contract = option_contracts.get(instrument_id)
            if contract is None:
                raise P567RC3CompatibilityError(f"option contract master missing: {instrument_id}")
            valid_from = _dt(contract.get("first_trade_date"), f"contract {instrument_id}.first_trade_date")
            expiration = _dt(contract.get("expiration"), f"contract {instrument_id}.expiration")
            valid_until = _optional_dt(contract.get("last_trade_date"), f"contract {instrument_id}.last_trade_date") or expiration
            exercise = self._exercise_style(contract.get("exercise_style"))
            settlement = self._settlement_type(contract.get("settlement_type"))
            source_payload = contract
        else:
            underlying = underlyings.get(instrument_id)
            if underlying is None:
                raise P567RC3CompatibilityError(f"underlying instrument master missing: {instrument_id}")
            valid_from = _dt(underlying.get("quote_time"), f"underlying {instrument_id}.quote_time")
            valid_until = p8_decision_time
            expiration = None
            exercise = ExerciseStyle.NONE
            settlement = SettlementType.NONE
            source_payload = underlying
        instrument_ref = builder.source(
            phase="P6",
            source_type=f"instrument_master_{instrument_id}",
            source=source_payload,
            relationship_type="INSTRUMENT_MASTER",
            available_at=_dt(source_payload.get("available_at") or source_payload.get("first_trade_date"), f"instrument {instrument_id}.available_at"),
        )
        return CandidateLegV1(
            instrument_id=instrument_id,
            instrument_type=instrument_type,
            side=side,
            unit_quantity=quantity,
            contract_multiplier=_decimal(leg.get("multiplier"), f"P6 leg {instrument_id}.multiplier"),
            strike=(None if leg.get("strike") is None else _decimal(leg.get("strike"), f"P6 leg {instrument_id}.strike")),
            expiration=expiration,
            exercise_style=exercise,
            settlement_type=settlement,
            contract_valid_from=valid_from,
            contract_valid_until=valid_until,
            instrument_master_ref=instrument_ref,
        )

    @staticmethod
    def _exercise_style(value: object) -> ExerciseStyle:
        normalized = str(value or "NONE").upper()
        return {
            "NONE": ExerciseStyle.NONE,
            "EUROPEAN": ExerciseStyle.EUROPEAN,
            "AMERICAN": ExerciseStyle.AMERICAN,
        }.get(normalized, ExerciseStyle.OTHER)

    @staticmethod
    def _settlement_type(value: object) -> SettlementType:
        normalized = str(value or "NONE").upper()
        return {"CASH": SettlementType.CASH, "PHYSICAL": SettlementType.PHYSICAL}.get(normalized, SettlementType.NONE)

    @staticmethod
    def _lifecycle_status(
        *,
        legs_source: Sequence[Any],
        scenario_rows: Sequence[Mapping[str, Any]],
    ) -> ComponentQualificationStatus:
        option_present = any(
            str(_mapping(leg, "leg").get("instrument_type", "")).upper() in {"OPTION", "CALL", "PUT"}
            or _mapping(leg, "leg").get("expiration") is not None
            for leg in legs_source
        )
        if not option_present:
            return ComponentQualificationStatus.QUALIFIED
        modelled = any(
            str(row.get("exercise_state")) not in {"NOT_MODELLED", "None", ""}
            or str(row.get("assignment_state")) not in {"NOT_MODELLED", "None", ""}
            for row in scenario_rows
        )
        return ComponentQualificationStatus.DEGRADED if modelled else ComponentQualificationStatus.UNAVAILABLE

    def _extract_p7_populations(
        self,
        *,
        p7: Mapping[str, Any],
        p6: Mapping[str, Any],
    ) -> dict[str, tuple[Mapping[str, Any], ...] | tuple[str, ...]]:
        candidates = _records(_mapping(_required(p6, "strategy_candidate_panel", "P6 outputs"), "P6 candidates"), "P6 candidates")
        received = tuple(str(row["candidate_id"]) for row in candidates)
        panels = {
            "ranked": _first_path(p7, ("finalization.s8.ranked_strategy_candidate_panel", "outputs.ranked_strategy_candidate_panel", "ranked_strategy_candidate_panel"), required=False, label="ranked panel"),
            "eligibility": _first_path(p7, ("foundation.comparison.outputs.eligibility_blocked_candidate_panel", "eligibility_blocked_candidate_panel"), required=False, label="eligibility panel"),
            "safety": _first_path(p7, ("finalization.s7.safety_blocked_candidate_panel", "outputs.safety_blocked_candidate_panel", "safety_blocked_candidate_panel"), required=False, label="safety panel"),
            "abstained": _first_path(p7, ("finalization.s7.abstained_candidate_panel", "outputs.abstained_candidate_panel", "abstained_candidate_panel"), required=False, label="abstained panel"),
            "final_blocked": _first_path(p7, ("finalization.s7.final_blocked_candidate_panel", "outputs.final_blocked_candidate_panel", "final_blocked_candidate_panel"), required=False, label="final blocked panel"),
        }
        rows = {key: (() if panel is None else _records(panel, f"P7 {key}")) for key, panel in panels.items()}
        ids = {key: {str(row["candidate_id"]) for row in values} for key, values in rows.items() if key != "final_blocked"}
        for name, values in ids.items():
            unknown = values - set(received)
            if unknown:
                raise P567RC3CompatibilityError(f"P7 {name} contains candidates absent from P6: {sorted(unknown)}")
        assigned = set().union(*ids.values()) if ids else set()
        if sum(len(values) for values in ids.values()) != len(assigned):
            raise P567RC3CompatibilityError("candidate appears in multiple P7 terminal populations")
        final_by_id = {str(row["candidate_id"]): row for row in cast(tuple[Mapping[str, Any], ...], rows["final_blocked"])}
        unassigned = set(received) - assigned
        for candidate_id in sorted(unassigned):
            row = final_by_id.get(candidate_id)
            if row is None:
                raise P567RC3CompatibilityError(f"P7 did not publish a terminal state for {candidate_id}")
            reason_codes = self._reason_codes(row)
            if any("SAFETY" in code or "LIMIT" in code or "LOSS" in code for code in reason_codes):
                rows["safety"] = cast(tuple[Mapping[str, Any], ...], rows["safety"]) + (row,)
            else:
                rows["eligibility"] = cast(tuple[Mapping[str, Any], ...], rows["eligibility"]) + (row,)
        final_sets = {
            name: {str(row["candidate_id"]) for row in cast(tuple[Mapping[str, Any], ...], rows[name])}
            for name in ("ranked", "eligibility", "safety", "abstained")
        }
        terminal_union = set().union(*final_sets.values())
        if terminal_union != set(received) or sum(len(values) for values in final_sets.values()) != len(received):
            raise P567RC3CompatibilityError("P7 candidate conservation does not close after RC3 adaptation")
        return {
            "received": received,
            "ranked": cast(tuple[Mapping[str, Any], ...], rows["ranked"]),
            "eligibility": cast(tuple[Mapping[str, Any], ...], rows["eligibility"]),
            "safety": cast(tuple[Mapping[str, Any], ...], rows["safety"]),
            "abstained": cast(tuple[Mapping[str, Any], ...], rows["abstained"]),
        }

    def _build_comparison_groups(
        self,
        *,
        p7: Mapping[str, Any],
        p6: Mapping[str, Any],
        populations: Mapping[str, Any],
    ) -> tuple[ComparisonGroupRecord, ...]:
        panel = _first_path(
            p7,
            ("foundation.comparison.outputs.candidate_comparison_group_panel", "candidate_comparison_group_panel"),
            required=True,
            label="candidate comparison groups",
        )
        assert panel is not None
        source_rows = _records(panel, "candidate comparison groups")
        candidate_rows = {
            str(row["candidate_id"]): row
            for row in _records(_mapping(p6["strategy_candidate_panel"], "P6 candidates"), "P6 candidates")
        }
        by_group: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in source_rows:
            by_group[_text(row.get("comparison_group_id"), "comparison_group_id")].append(row)
        received = set(cast(tuple[str, ...], populations["received"]))
        group_members = {str(row["candidate_id"]) for row in source_rows}
        if group_members != received:
            raise P567RC3CompatibilityError("P7 comparison groups do not cover exactly the received candidates")
        groups: list[ComparisonGroupRecord] = []
        for group_id, rows in sorted(by_group.items()):
            objective_values = {str(row.get("objective_family")) for row in rows}
            horizon_values = {str(row.get("horizon")) for row in rows}
            policy_values = {f"{row.get('policy_id')}@{row.get('policy_version')}" for row in rows}
            if len(objective_values) != 1 or len(horizon_values) != 1 or len(policy_values) != 1:
                raise P567RC3CompatibilityError(f"inconsistent comparison group semantics: {group_id}")
            members = tuple(sorted(str(row["candidate_id"]) for row in rows))
            underlying_scope = tuple(sorted({str(candidate_rows[candidate_id]["underlying_id"]) for candidate_id in members}))
            capital_buckets = {str(row.get("capital_at_risk_bucket")) for row in rows if row.get("capital_at_risk_bucket") is not None}
            groups.append(
                ComparisonGroupRecord(
                    comparison_group_id=group_id,
                    objective_family=next(iter(objective_values)),
                    underlying_scope=underlying_scope,
                    horizon_scope=next(iter(horizon_values)),
                    capital_at_risk_bucket=(next(iter(capital_buckets)) if len(capital_buckets) == 1 else None),
                    liquidity_bucket=None,
                    member_candidate_ids=members,
                    comparability_policy_id=next(iter(policy_values)),
                )
            )
        return tuple(groups)

    @staticmethod
    def _reason_codes(row: Mapping[str, Any]) -> tuple[str, ...]:
        raw = row.get("reason_codes") or row.get("blocking_reason_codes") or row.get("group_reason_codes") or ()
        return tuple(str(value) for value in _sequence(raw, "reason_codes")) or ("P7_RC3_TERMINAL_STATE",)

    def _build_receipt(
        self,
        *,
        builder: _ArtifactBuilder,
        p8_run_id: str,
        p8_cycle_id: str,
        p8_decision_time: datetime,
        computed_at: datetime,
        p5_release: str,
        p6_release: str,
        p7_release: str,
        populations: Mapping[str, Any],
    ) -> P567RC3AdaptationReceiptV1:
        provisional = P567RC3AdaptationReceiptV1(
            receipt_id=f"p567rc3-receipt-{p8_run_id}-{p8_cycle_id}",
            contract_version="P567_RC3_TO_P8_ADAPTATION_RECEIPT_V1",
            schema_version="1.0.0",
            adapter_id=ADAPTER_ID,
            adapter_release=ADAPTER_RELEASE,
            run_id=p8_run_id,
            cycle_id=p8_cycle_id,
            decision_time=p8_decision_time,
            computed_at=computed_at,
            source_p5_release=p5_release,
            source_p6_release=p6_release,
            source_p7_release=p7_release,
            source_artifacts=tuple(builder.audit_records),
            received_candidate_ids=cast(tuple[str, ...], populations["received"]),
            ranked_candidate_ids=tuple(str(row["candidate_id"]) for row in cast(tuple[Mapping[str, Any], ...], populations["ranked"])),
            eligibility_blocked_candidate_ids=tuple(str(row["candidate_id"]) for row in cast(tuple[Mapping[str, Any], ...], populations["eligibility"])),
            safety_blocked_candidate_ids=tuple(str(row["candidate_id"]) for row in cast(tuple[Mapping[str, Any], ...], populations["safety"])),
            abstained_candidate_ids=tuple(str(row["candidate_id"]) for row in cast(tuple[Mapping[str, Any], ...], populations["abstained"])),
            transformations=(
                "RC3_SOURCE_ARTIFACTS_WRAPPED_WITH_P8_RAW_CONTENT_HASHES",
                "P5_RC3_PUBLICATION_MATERIALIZED_AS_P5_BELIEF_EVIDENCE_BUNDLE_V1",
                "P6_RC3_PANELS_MATERIALIZED_AS_UNIT_ECONOMIC_PACKAGES",
                "P7_RC3_CARDINAL_INTERNAL_SCORES_DOWNCAST_TO_ORDINAL_PREFERENCES",
                "P7_RC3_TERMINAL_POPULATIONS_RECONCILED_AGAINST_P6_RECEIVED_SET",
                "P8_PUBLICATION_CLOCKS_CREATED_WITHOUT_REUSING_RC3_AVAILABLE_AT_SEMANTICS",
            ),
            warnings=(
                "P6_RC3_LOT_SIZE_AND_QUANTITY_INCREMENT_USE_EXPLICIT_ONE_CANDIDATE_UNIT_BRIDGE_POLICY",
                "P6_RC3_LIQUIDITY_SCORE_IS_NOT_CONVERTED_TO_CAPACITY_UNITS",
                "P7_RC3_CONFIDENCE_IS_UNCALIBRATED_UNLESS_CONTENT_ADDRESSED_CALIBRATION_EVIDENCE_IS_AVAILABLE",
            ),
            content_sha256="0" * 64,
        )
        return finalize_content_hash(provisional)

    def _build_handoff(
        self,
        *,
        populations: Mapping[str, Any],
        groups: tuple[ComparisonGroupRecord, ...],
        p6_refs: Mapping[str, ArtifactReference],
        p7_source_refs: Mapping[str, ArtifactReference],
        receipt_ref: ArtifactReference,
        p8_run_id: str,
        p8_cycle_id: str,
        p7_decision_time: datetime,
        market_cutoff_at: datetime,
        computed_at: datetime,
        recorded_at: datetime,
        available_at: datetime,
        p7_release: str,
    ) -> P7RankingHandoffV1:
        trace_ref = p7_source_refs.get("ranking_trace_panel") or p7_source_refs.get("ranked_strategy_candidate_panel")
        if cast(tuple[Mapping[str, Any], ...], populations["ranked"]) and trace_ref is None:
            raise P567RC3CompatibilityError("ranked RC3 candidates require a decision trace artifact")
        thesis_ref = p7_source_refs.get("strategy_thesis_card_panel")
        decomposition_ref = p7_source_refs.get("score_decomposition_panel")
        ranked = tuple(
            RankedCandidateRecord(
                candidate_id=str(row["candidate_id"]),
                canonical_candidate_id=str(row["candidate_id"]),
                comparison_group_id=_text(row.get("comparison_group_id"), "ranked comparison_group_id"),
                rank=int(row.get("rank_position") or row.get("rank") or 0),
                rank_tier=f"RC3_RANK_{int(row.get('rank_position') or row.get('rank') or 0)}",
                score_semantics=ScoreSemantics.ORDINAL,
                score_value=None,
                confidence_state=ConfidenceState.UNCALIBRATED,
                confidence_calibration_ref=None,
                p6_economic_package_ref=p6_refs[str(row["candidate_id"])],
                decision_trace_ref=cast(ArtifactReference, trace_ref),
                thesis_card_ref=thesis_ref,
                score_decomposition_ref=decomposition_ref,
            )
            for row in cast(tuple[Mapping[str, Any], ...], populations["ranked"])
        )

        def terminal(rows: tuple[Mapping[str, Any], ...], state: P7TerminalState) -> tuple[P7TerminalCandidateRecord, ...]:
            return tuple(
                P7TerminalCandidateRecord(
                    candidate_id=str(row["candidate_id"]),
                    terminal_state=state,
                    reason_codes=self._reason_codes(row),
                    p6_economic_package_ref=p6_refs[str(row["candidate_id"])],
                )
                for row in rows
            )

        artifact_refs = tuple(sorted({ref.artifact_id: ref for ref in (*p7_source_refs.values(), receipt_ref)}.values(), key=lambda ref: ref.artifact_id))
        provisional = P7RankingHandoffV1(
            handoff_id=f"p7-to-p8-rc3-bridge-{p8_run_id}-{p8_cycle_id}",
            contract_version="P7_TO_P8_RANKING_HANDOFF_V1",
            schema_version="1.0.0",
            producer_phase="P7",
            producer_release=f"{p7_release}+{ADAPTER_ID}@{ADAPTER_RELEASE}",
            run_id=p8_run_id,
            cycle_id=p8_cycle_id,
            decision_time=p7_decision_time,
            market_cutoff_at=market_cutoff_at,
            computed_at=computed_at,
            recorded_at=recorded_at,
            available_at=available_at,
            content_sha256="0" * 64,
            received_candidate_ids=cast(tuple[str, ...], populations["received"]),
            ranked=ranked,
            eligibility_blocked=terminal(cast(tuple[Mapping[str, Any], ...], populations["eligibility"]), P7TerminalState.ELIGIBILITY_BLOCKED),
            safety_blocked=terminal(cast(tuple[Mapping[str, Any], ...], populations["safety"]), P7TerminalState.SAFETY_BLOCKED),
            abstained=terminal(cast(tuple[Mapping[str, Any], ...], populations["abstained"]), P7TerminalState.ABSTAINED),
            comparison_groups=groups,
            artifact_refs=artifact_refs,
        )
        return finalize_content_hash(provisional)


def adapt_p567_rc3_to_p8(**kwargs: Any) -> P567RC3AdaptationResult:
    """Convenience functional API for :class:`P567RC3Adapter`."""

    return P567RC3Adapter().adapt(**kwargs)
