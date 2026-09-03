from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any
import json

import yaml

from .modules._module_executor import ContractValidationError
from .modules._s2_temporal import parse_as_of_cutoff, parse_datetime_utc
from .modules._p2_semantic_helpers import FORBIDDEN


PHASE2_PANELS = (
    "source_quality_panel",
    "clean_context_source_panel",
    "clean_document_panel",
    "clean_event_reference_panel",
    "clean_underlying_panel",
    "clean_underlying_trade_panel",
    "clean_macro_br_panel",
    "clean_macro_us_panel",
    "clean_benchmark_panel",
    "clean_calendar_panel",
    "clean_corporate_actions_panel",
    "clean_option_contract_panel",
    "clean_option_quotes_panel",
    "clean_cost_reference_panel",
    "clean_liquidity_reference_panel",
)

STATUS_ORDER = {"PASS": 0, "WARN": 1, "DEGRADED": 2, "BLOCK": 3}

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_ROOT = PACKAGE_ROOT / "schemas"


@dataclass(frozen=True)
class QualityIssue:
    code: str
    severity: str
    panel: str
    message: str
    record_key: str | None = None


@dataclass(frozen=True)
class PanelEvaluation:
    panel_name: str
    status: str
    record_count: int
    checks: dict[str, str]
    issues: list[QualityIssue]
    metrics: dict[str, Any]


def _status_for(issues: list[QualityIssue]) -> str:
    if not issues:
        return "PASS"
    return max((issue.severity for issue in issues), key=lambda value: STATUS_ORDER[value])


def _raise_if_bad_artifact(name: str, value: Any) -> dict:
    if not isinstance(value, dict):
        raise ContractValidationError(f"{name} must be a materialized artifact dict")
    if value.get("source"):
        raise ContractValidationError(f"{name} cannot be synthesized from source")
    if not value.get("artifact_id"):
        raise ContractValidationError(f"{name} requires artifact_id")
    return value


def optional_records(value: Any, name: str) -> list[dict]:
    artifact = _raise_if_bad_artifact(name, value)
    for key in ("records", "rows", "items", "sources"):
        rows = artifact.get(key)
        if isinstance(rows, list):
            return [dict(item) for item in rows if isinstance(item, dict)]
    return []


def _scan_forbidden(value: Any, panel: str, path: str = "root") -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    if isinstance(value, dict):
        leaked = sorted(set(value).intersection(FORBIDDEN))
        for field in leaked:
            issues.append(
                QualityIssue(
                    code="P2Q_FORBIDDEN_FIELD",
                    severity="BLOCK",
                    panel=panel,
                    message=f"forbidden field {field!r} found at {path}",
                    record_key=path,
                )
            )
        for key, item in value.items():
            issues.extend(_scan_forbidden(item, panel, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            issues.extend(_scan_forbidden(item, panel, f"{path}[{index}]"))
    return issues


def _schema(name: str) -> dict:
    path = SCHEMA_ROOT / f"{name}.schema.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _schema_issues(name: str, artifact: dict, rows: list[dict], config: dict) -> list[QualityIssue]:
    schema = _schema(name)
    required = list(schema.get("required_fields", []))
    if not required:
        return []

    # Empty optional panels have no row contract to validate. Their readiness
    # is handled by _empty_policy_issues and target-specific gates; reporting
    # every legacy row field as missing here incorrectly degraded unrelated
    # handoffs such as P3 when only P6 quotes were unavailable.
    if not rows:
        return []

    issues: list[QualityIssue] = []
    # RC4.1 schemas mix artifact-envelope fields and row fields. Missing legacy fields
    # are warnings here; causal/referential violations are blocked independently below.
    for field in required:
        # RC4.1 schemas declare structural presence, not universal non-nullability.
        # A field such as bid/ask may be intentionally unknown; requiring a
        # non-null value would force exactly the fabricated defaults P2 is meant
        # to eliminate. Strict mode therefore blocks only true schema absence.
        present_top = field in artifact
        present_rows = bool(rows) and all(field in row for row in rows)
        if not present_top and not present_rows:
            issues.append(
                QualityIssue(
                    code="P2Q_SCHEMA_LEGACY_MISSING_FIELD",
                    severity="BLOCK" if config.get("strict_schema_validation", False) else "WARN",
                    panel=name,
                    message=f"required schema field {field!r} is not materialized",
                )
            )
    return issues


def _parse_datetime(value: Any, *, date_only_policy: str = "start_of_day") -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return parse_datetime_utc(
            value,
            field="quality_timestamp",
            date_only_policy=date_only_policy,
            timezone_name="UTC",
            strict=False,
        )
    except ContractValidationError:
        return None

def _temporal_issues(name: str, rows: list[dict], config: dict) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    config_as_of = parse_as_of_cutoff(config.get("as_of_date"), config)
    for index, row in enumerate(rows):
        available_raw = row.get("available_at") or row.get("declared_available_at")
        if available_raw not in (None, ""):
            available = _parse_datetime(available_raw, date_only_policy="end_of_day")
            if available is None:
                issues.append(
                    QualityIssue(
                        code="P2Q_INVALID_AVAILABLE_AT",
                        severity="BLOCK",
                        panel=name,
                        message="available_at is not parseable",
                        record_key=str(index),
                    )
                )
                continue
            row_as_of = parse_as_of_cutoff(row.get("as_of_date"), config) or config_as_of
            if row_as_of is not None and available > row_as_of:
                issues.append(
                    QualityIssue(
                        code="P2Q_FUTURE_DATA",
                        severity="BLOCK",
                        panel=name,
                        message="available_at is later than the applicable as_of cutoff",
                        record_key=str(index),
                    )
                )
    return issues


def _grain_fields(name: str) -> tuple[str, ...]:
    overrides = {
        "clean_underlying_panel": ("date", "underlying"),
        "clean_underlying_trade_panel": ("date", "underlying"),
        "clean_document_panel": ("document_id",),
        "clean_event_reference_panel": ("event_id",),
        "clean_option_contract_panel": ("contract_key",),
        "clean_option_quotes_panel": ("date", "contract_key"),
    }
    if name in overrides:
        return overrides[name]
    grain = _schema(name).get("grain", [])
    # artifact_id is envelope-level in several legacy schemas and is not a row business key.
    values = tuple(field for field in grain if field not in {"artifact_id", "created_at"})
    return values


def _duplicate_issues(name: str, rows: list[dict]) -> list[QualityIssue]:
    fields = _grain_fields(name)
    if not fields:
        return []
    seen: dict[tuple, dict] = {}
    issues: list[QualityIssue] = []
    for index, row in enumerate(rows):
        if any(row.get(field) in (None, "") for field in fields):
            continue
        key = tuple(row.get(field) for field in fields)
        previous = seen.get(key)
        if previous is None:
            seen[key] = row
            continue
        same = json.dumps(previous, sort_keys=True, default=str) == json.dumps(row, sort_keys=True, default=str)
        issues.append(
            QualityIssue(
                code="P2Q_DUPLICATE_KEY" if same else "P2Q_CONFLICTING_DUPLICATE_KEY",
                severity="WARN" if same else "BLOCK",
                panel=name,
                message=f"duplicate business key for fields {fields}",
                record_key=str(key),
            )
        )
    return issues


def _basic_numeric_issues(name: str, rows: list[dict]) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    nonnegative_fields = {
        "open", "high", "low", "close", "reference_price_t", "last_price",
        "bid", "ask", "volume", "financial_volume", "open_interest", "strike",
        "contract_size", "cost_estimate", "liquidity_score",
    }
    for index, row in enumerate(rows):
        for field in nonnegative_fields:
            value = row.get(field)
            if value in (None, ""):
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            if numeric < 0:
                issues.append(
                    QualityIssue(
                        code="P2Q_NEGATIVE_MARKET_VALUE",
                        severity="BLOCK",
                        panel=name,
                        message=f"{field} must not be negative",
                        record_key=str(index),
                    )
                )
        if row.get("bid") not in (None, "") and row.get("ask") not in (None, ""):
            try:
                if float(row["bid"]) > float(row["ask"]):
                    issues.append(
                        QualityIssue(
                            code="P2Q_CROSSED_QUOTE",
                            severity="BLOCK",
                            panel=name,
                            message="bid exceeds ask",
                            record_key=str(index),
                        )
                    )
            except (TypeError, ValueError):
                pass
    return issues


def _empty_policy_issues(name: str, rows: list[dict], config: dict) -> list[QualityIssue]:
    if rows:
        return []
    expected_domains = set(config.get("expected_domains", []))
    required = {"source_quality_panel"}
    if "market" in expected_domains:
        required.update({"clean_underlying_panel", "clean_calendar_panel"})
    if "options" in expected_domains:
        required.update({"clean_option_contract_panel", "clean_option_quotes_panel"})
    if "context" in expected_domains:
        # At least one S5 panel is needed; handled as target readiness, not per-panel.
        pass
    if name in required:
        return [
            QualityIssue(
                code="P2Q_EMPTY_REQUIRED_PANEL",
                severity="BLOCK",
                panel=name,
                message="panel is empty but required by the declared run profile",
            )
        ]
    return []


def evaluate_panel(name: str, artifact: dict, config: dict) -> PanelEvaluation:
    rows = optional_records(artifact, name)
    issues: list[QualityIssue] = []
    issues.extend(_scan_forbidden(artifact, name))
    issues.extend(_schema_issues(name, artifact, rows, config))
    issues.extend(_temporal_issues(name, rows, config))
    issues.extend(_duplicate_issues(name, rows))
    issues.extend(_basic_numeric_issues(name, rows))
    issues.extend(_empty_policy_issues(name, rows, config))

    checks = {
        "artifact_envelope": "PASS",
        "forbidden_fields": "BLOCK" if any(i.code == "P2Q_FORBIDDEN_FIELD" for i in issues) else "PASS",
        "schema": (
            "BLOCK" if any(i.code.startswith("P2Q_SCHEMA_") and i.severity == "BLOCK" for i in issues)
            else ("WARN" if any(i.code.startswith("P2Q_SCHEMA_") for i in issues) else "PASS")
        ),
        "temporal": "BLOCK" if any(i.code in {"P2Q_INVALID_AVAILABLE_AT", "P2Q_FUTURE_DATA"} for i in issues) else "PASS",
        "duplicates": "BLOCK" if any(i.code == "P2Q_CONFLICTING_DUPLICATE_KEY" for i in issues) else ("WARN" if any(i.code == "P2Q_DUPLICATE_KEY" for i in issues) else "PASS"),
        "market_sanity": "BLOCK" if any(i.code in {"P2Q_NEGATIVE_MARKET_VALUE", "P2Q_CROSSED_QUOTE"} for i in issues) else "PASS",
        "coverage": "BLOCK" if any(i.code == "P2Q_EMPTY_REQUIRED_PANEL" for i in issues) else "PASS",
    }
    return PanelEvaluation(
        panel_name=name,
        status=_status_for(issues),
        record_count=len(rows),
        checks=checks,
        issues=issues,
        metrics={},
    )


def _cross_panel_issues(inputs: dict, config: dict) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    panels = {name: optional_records(inputs[name], name) for name in PHASE2_PANELS}

    # S5 source references should resolve to a quality record when the quality registry is populated.
    quality_ids = {str(row.get("source_id")) for row in panels["source_quality_panel"] if row.get("source_id") not in (None, "")}
    if quality_ids:
        for panel_name in ("clean_context_source_panel", "clean_document_panel", "clean_event_reference_panel"):
            for index, row in enumerate(panels[panel_name]):
                source_id = row.get("source_id")
                if source_id not in (None, "") and str(source_id) not in quality_ids:
                    explicit_unknown = str(row.get("quality_status") or row.get("source_quality_status") or "").lower() in {"unknown", "unknown_source"}
                    issues.append(
                        QualityIssue(
                            code="P2Q_ORPHAN_SOURCE",
                            severity="WARN" if explicit_unknown else "DEGRADED",
                            panel=panel_name,
                            message=f"source_id {source_id!r} is not present in source_quality_panel",
                            record_key=str(index),
                        )
                    )

    # Option quote -> contract integrity.
    contract_keys = {str(row.get("contract_key")) for row in panels["clean_option_contract_panel"] if row.get("contract_key") not in (None, "")}
    if contract_keys or panels["clean_option_quotes_panel"]:
        for index, row in enumerate(panels["clean_option_quotes_panel"]):
            key = row.get("contract_key")
            if key in (None, ""):
                continue
            if str(key) not in contract_keys:
                issues.append(
                    QualityIssue(
                        code="P2Q_ORPHAN_OPTION_QUOTE",
                        severity="BLOCK",
                        panel="clean_option_quotes_panel",
                        message=f"quote references unknown contract_key {key!r}",
                        record_key=str(index),
                    )
                )

    # Underlying-trade records should resolve to the cleaned underlying panel when both expose keys.
    underlying_keys = {
        (str(row.get("underlying")), str(row.get("date")))
        for row in panels["clean_underlying_panel"]
        if row.get("underlying") not in (None, "") and row.get("date") not in (None, "")
    }
    if underlying_keys:
        for index, row in enumerate(panels["clean_underlying_trade_panel"]):
            if row.get("underlying") in (None, "") or row.get("date") in (None, ""):
                continue
            key = (str(row["underlying"]), str(row["date"]))
            if key not in underlying_keys:
                issues.append(
                    QualityIssue(
                        code="P2Q_ORPHAN_UNDERLYING_TRADE",
                        severity="BLOCK",
                        panel="clean_underlying_trade_panel",
                        message=f"trade row has no matching clean_underlying_panel row for {key}",
                        record_key=str(index),
                    )
                )

    # Calendar vs tradability consistency when a comparable date key is available.
    calendar_by_date: dict[str, bool] = {}
    for row in panels["clean_calendar_panel"]:
        date = row.get("date")
        flag = row.get("is_trading_day")
        if flag is None:
            flag = row.get("trading_day_flag")
        if date not in (None, "") and isinstance(flag, bool):
            calendar_by_date[str(date)] = flag
    for index, row in enumerate(panels["clean_underlying_trade_panel"]):
        date = row.get("date")
        tradable = row.get("tradability_flag")
        if date not in (None, "") and tradable is True and calendar_by_date.get(str(date)) is False:
            issues.append(
                QualityIssue(
                    code="P2Q_CALENDAR_TRADABILITY_CONFLICT",
                    severity="BLOCK",
                    panel="clean_underlying_trade_panel",
                    message="tradability_flag is true on a non-trading calendar date",
                    record_key=str(index),
                )
            )

    # Operational corporate actions must not be duplicated by S5 as a second canonical truth.
    for index, row in enumerate(panels["clean_event_reference_panel"]):
        domain = str(row.get("record_domain") or row.get("domain") or "").lower()
        event_type = str(row.get("event_type") or "").lower()
        if domain == "corporate_action" or event_type == "corporate_action":
            issues.append(
                QualityIssue(
                    code="P2Q_S5_OPERATIONAL_CORPORATE_ACTION",
                    severity="DEGRADED",
                    panel="clean_event_reference_panel",
                    message="S5 event panel contains an operational corporate_action record owned by S3",
                    record_key=str(index),
                )
            )

    return issues


def _target_readiness(inputs: dict, panel_results: dict[str, PanelEvaluation], cross_issues: list[QualityIssue]) -> dict[str, dict]:
    rows = {name: optional_records(inputs[name], name) for name in PHASE2_PANELS}

    def status_for_panels(names: tuple[str, ...], extra: list[QualityIssue] | None = None) -> str:
        statuses = [panel_results[name].status for name in names]
        if extra:
            statuses.extend(issue.severity for issue in extra)
        return max(statuses, key=lambda value: STATUS_ORDER[value]) if statuses else "PASS"

    p3_names = ("clean_context_source_panel", "clean_document_panel", "clean_event_reference_panel", "source_quality_panel")
    p3_status = status_for_panels(p3_names)
    if not any(rows[name] for name in p3_names[:3]):
        p3_status = "BLOCK"

    p4_names = (
        "clean_underlying_panel", "clean_macro_br_panel", "clean_macro_us_panel",
        "clean_benchmark_panel", "clean_calendar_panel", "clean_corporate_actions_panel",
    )
    p4_status = status_for_panels(p4_names)
    if not rows["clean_underlying_panel"]:
        p4_status = "BLOCK"

    p6_names = (
        "clean_option_contract_panel", "clean_option_quotes_panel", "clean_underlying_trade_panel",
        "clean_calendar_panel", "clean_cost_reference_panel", "clean_liquidity_reference_panel",
    )
    p6_status = status_for_panels(p6_names)
    has_contracts = bool(rows["clean_option_contract_panel"])
    has_quotes = bool(rows["clean_option_quotes_panel"])
    if has_contracts != has_quotes:
        p6_status = "BLOCK"
    elif not has_contracts and not has_quotes:
        p6_status = max((p6_status, "DEGRADED"), key=lambda value: STATUS_ORDER[value])

    # Critical cross-panel issues affect the corresponding target paths.
    for issue in cross_issues:
        if issue.severity == "BLOCK":
            if issue.panel in {"clean_context_source_panel", "clean_document_panel", "clean_event_reference_panel", "source_quality_panel"}:
                p3_status = "BLOCK"
            if issue.panel in {"clean_underlying_panel", "clean_calendar_panel", "clean_corporate_actions_panel"}:
                p4_status = "BLOCK"
            if issue.panel in {"clean_option_contract_panel", "clean_option_quotes_panel", "clean_underlying_trade_panel", "clean_cost_reference_panel", "clean_liquidity_reference_panel", "clean_calendar_panel"}:
                p6_status = "BLOCK"

    return {
        "phase_03_agents_rag_memory": {"status": p3_status},
        "phase_04_feature_base": {"status": p4_status},
        "phase_06_candidate_generation": {"status": p6_status},
    }


def evaluate_phase2_quality(inputs: dict, config: dict | None = None) -> dict:
    config = config or {}
    panel_results = {name: evaluate_panel(name, inputs[name], config) for name in PHASE2_PANELS}
    cross_issues = _cross_panel_issues(inputs, config)

    all_issues = [issue for result in panel_results.values() for issue in result.issues] + cross_issues
    overall_status = _status_for(all_issues)
    quality_flags = {name: result.status for name, result in panel_results.items()}
    panel_counts = {name: result.record_count for name, result in panel_results.items()}

    blocking = [asdict(issue) for issue in all_issues if issue.severity == "BLOCK"]
    warnings = [asdict(issue) for issue in all_issues if issue.severity in {"WARN", "DEGRADED"}]
    target_readiness = _target_readiness(inputs, panel_results, cross_issues)

    return {
        "panel_counts": panel_counts,
        "quality_flags": quality_flags,
        "all_official_panels_covered": set(inputs).issuperset(PHASE2_PANELS),
        "quality_flags_summarized": True,
        "status": overall_status,
        "panel_results": {
            name: {
                "status": result.status,
                "record_count": result.record_count,
                "checks": dict(result.checks),
                "issues": [asdict(issue) for issue in result.issues],
                "metrics": dict(result.metrics),
            }
            for name, result in panel_results.items()
        },
        "cross_panel_issues": [asdict(issue) for issue in cross_issues],
        "blocking_issues": blocking,
        "warnings": warnings,
        "metrics": {
            "total_records_evaluated": sum(panel_counts.values()),
            "blocking_issue_count": len(blocking),
            "warning_or_degraded_issue_count": len(warnings),
        },
        "target_readiness": target_readiness,
        "p2_semantics_version": "p2.quality.v2",
    }
