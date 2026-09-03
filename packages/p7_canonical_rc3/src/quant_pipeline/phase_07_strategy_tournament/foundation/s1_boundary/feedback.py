"""P7.S1.M04 — load only promoted, previous-cycle P9 feedback."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from ..artifacts import ArtifactEnvelope, create_artifact, verify_artifact_hash
from ..errors import P7S1Error
from ..models import FeedbackManifest, FeedbackRecord, ModuleConfig
from ..reason_codes import ReasonCode
from .common import walk_json

MODULE_ID = "P7.S1.M04"
FEEDBACK_FORBIDDEN_FIELDS = {
    "rank",
    "candidate_score",
    "desired_rank",
    "realized_outcome",
    "realized_pnl",
    "future_return",
    "portfolio_weight",
    "final_position_size",
}


class FeedbackPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    allowed_scope: dict[str, JsonValue] = Field(default_factory=dict)


def execute(
    report_payload: dict[str, JsonValue] | None,
    manifest_payload: dict[str, JsonValue] | None,
    config_payload: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    config, policy = _parse_config(config_payload)
    if report_payload is None and manifest_payload is None:
        return _empty_outputs(config)
    report, manifest, records = _parse_feedback(report_payload, manifest_payload)
    _validate_manifest(report, manifest, config)
    accepted = _validate_records(records, manifest, config, policy)
    return _build_outputs(config, manifest, accepted)


def _parse_config(config_payload):
    try:
        config = ModuleConfig.model_validate(config_payload)
        policy = FeedbackPolicy.model_validate(config.policy)
    except ValidationError as exc:
        raise P7S1Error(
            ReasonCode.FEEDBACK_SCOPE_MISMATCH,
            "feedback module configuration is invalid",
            MODULE_ID,
            {"errors": exc.errors(include_url=False)},
        ) from exc
    return config, policy


def _parse_feedback(report_payload, manifest_payload):
    if report_payload is None or manifest_payload is None:
        raise P7S1Error(
            ReasonCode.FEEDBACK_EVIDENCE_MISSING,
            "feedback report and manifest must be supplied together",
            MODULE_ID,
        )
    try:
        report = ArtifactEnvelope.model_validate(report_payload)
        manifest = FeedbackManifest.model_validate(manifest_payload)
        _precheck_raw_records(report.records)
        records = tuple(FeedbackRecord.model_validate(item) for item in report.records)
    except ValidationError as exc:
        raise P7S1Error(
            ReasonCode.FEEDBACK_EVIDENCE_MISSING,
            "feedback report or manifest failed validation",
            MODULE_ID,
            {"errors": exc.errors(include_url=False)},
        ) from exc
    return report, manifest, records



def _precheck_raw_records(records) -> None:
    hits = []
    for index, record in enumerate(records):
        for path, _ in walk_json(record):
            field = path.rsplit(".", maxsplit=1)[-1].lower()
            if field in FEEDBACK_FORBIDDEN_FIELDS:
                hits.append(f"$.records[{index}]{path[1:]}")
    if hits:
        raise P7S1Error(
            ReasonCode.FEEDBACK_SCOPE_MISMATCH,
            "feedback contains direct rank, score, realized or portfolio decisions",
            MODULE_ID,
            {"paths": hits[:50]},
        )

def _validate_records(records, manifest, config, policy):
    seen: set[str] = set()
    accepted: list[dict[str, JsonValue]] = []
    for record in records:
        if record.feedback_id in seen:
            raise P7S1Error(
                ReasonCode.FEEDBACK_DUPLICATE,
                "feedback IDs must be unique",
                MODULE_ID,
                {"feedback_id": record.feedback_id},
            )
        seen.add(record.feedback_id)
        _validate_record(record, manifest, config, policy)
        accepted.append(record.model_dump(mode="json"))
    accepted.sort(key=lambda item: str(item["feedback_id"]))
    return accepted


def _build_outputs(config, manifest, accepted):
    context = create_artifact(
        artifact_name="ranking_feedback_context",
        records=accepted,
        producer_module_id=MODULE_ID,
        context=config.context,
        grain="one_record_per_promoted_feedback_item",
        capability_status="AVAILABLE" if accepted else "UNAVAILABLE",
    )
    validation = create_artifact(
        artifact_name="feedback_validation_report",
        records=[
            {
                "status": "PASS",
                "feedback_status": "LOADED" if accepted else "EMPTY_VALID",
                "accepted_count": len(accepted),
                "source_cycle_id": manifest.source_cycle_id,
                "target_cycle_id": manifest.target_cycle_id,
            }
        ],
        producer_module_id=MODULE_ID,
        context=config.context,
        grain="one_record_per_feedback_load",
    )
    return {
        "ranking_feedback_context": context.model_dump(mode="json"),
        "feedback_validation_report": validation.model_dump(mode="json"),
    }


def _validate_manifest(report, manifest, config) -> None:
    if manifest.promotion_status != "PROMOTED":
        raise P7S1Error(
            ReasonCode.FEEDBACK_NOT_PROMOTED,
            "feedback manifest is not promoted",
            MODULE_ID,
        )
    if manifest.source_cycle_sequence >= manifest.target_cycle_sequence:
        raise P7S1Error(
            ReasonCode.FEEDBACK_CURRENT_CYCLE,
            "feedback must come from a strictly earlier cycle",
            MODULE_ID,
        )
    if manifest.target_cycle_id != config.context.cycle_id:
        raise P7S1Error(
            ReasonCode.FEEDBACK_SCOPE_MISMATCH,
            "feedback target cycle does not match the current P7 cycle",
            MODULE_ID,
        )
    if manifest.report_artifact_id != report.artifact_id:
        raise P7S1Error(
            ReasonCode.FEEDBACK_EVIDENCE_MISSING,
            "feedback manifest references another report artifact",
            MODULE_ID,
        )
    if manifest.report_content_sha256 != report.content_sha256 or not verify_artifact_hash(report):
        raise P7S1Error(
            ReasonCode.FEEDBACK_EVIDENCE_MISSING,
            "feedback report hash does not reconcile",
            MODULE_ID,
        )


def _validate_record(record, manifest, config, policy) -> None:
    _validate_record_cycles(record, manifest)
    if record.expires_at is not None and record.expires_at < config.context.decision_time:
        raise P7S1Error(
            ReasonCode.FEEDBACK_EXPIRED,
            "feedback expired before decision_time",
            MODULE_ID,
            {"feedback_id": record.feedback_id},
        )
    _validate_scope(record, policy)
    _reject_forbidden_feedback_fields(record)


def _validate_record_cycles(record, manifest) -> None:
    if record.promotion_status != "PROMOTED":
        raise P7S1Error(
            ReasonCode.FEEDBACK_NOT_PROMOTED,
            "only promoted feedback may enter P7",
            MODULE_ID,
            {"feedback_id": record.feedback_id},
        )
    if record.source_cycle_sequence >= record.target_cycle_sequence:
        raise P7S1Error(
            ReasonCode.FEEDBACK_CURRENT_CYCLE,
            "feedback record is not previous-cycle",
            MODULE_ID,
            {"feedback_id": record.feedback_id},
        )
    if record.source_cycle_id != manifest.source_cycle_id or record.target_cycle_id != manifest.target_cycle_id:
        raise P7S1Error(
            ReasonCode.FEEDBACK_SCOPE_MISMATCH,
            "feedback record cycle identity conflicts with manifest",
            MODULE_ID,
            {"feedback_id": record.feedback_id},
        )


def _validate_scope(record, policy) -> None:
    for key, expected in policy.allowed_scope.items():
        actual = record.scope.get(key)
        if actual is not None and actual != expected:
            raise P7S1Error(
                ReasonCode.FEEDBACK_SCOPE_MISMATCH,
                "feedback scope is outside the configured P7 scope",
                MODULE_ID,
                {"feedback_id": record.feedback_id, "key": key},
            )


def _reject_forbidden_feedback_fields(record) -> None:
    raw = record.model_dump(mode="json")
    hits = [
        path
        for path, _ in walk_json(raw)
        if path.rsplit(".", maxsplit=1)[-1].lower() in FEEDBACK_FORBIDDEN_FIELDS
    ]
    if hits:
        raise P7S1Error(
            ReasonCode.FEEDBACK_SCOPE_MISMATCH,
            "feedback contains direct rank, score, realized or portfolio decisions",
            MODULE_ID,
            {"feedback_id": record.feedback_id, "paths": hits},
        )


def _empty_outputs(config) -> dict[str, JsonValue]:
    context = create_artifact(
        artifact_name="ranking_feedback_context",
        records=[],
        producer_module_id=MODULE_ID,
        context=config.context,
        grain="one_record_per_promoted_feedback_item",
        capability_status="UNAVAILABLE",
    )
    validation = create_artifact(
        artifact_name="feedback_validation_report",
        records=[{"status": "PASS", "feedback_status": "ABSENT_OPTIONAL", "accepted_count": 0}],
        producer_module_id=MODULE_ID,
        context=config.context,
        grain="one_record_per_feedback_load",
    )
    return {
        "ranking_feedback_context": context.model_dump(mode="json"),
        "feedback_validation_report": validation.model_dump(mode="json"),
    }
