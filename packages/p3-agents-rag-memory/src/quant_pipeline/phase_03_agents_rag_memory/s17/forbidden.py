from __future__ import annotations

from collections.abc import Mapping, Sequence

from .errors import ForbiddenFieldError

FORBIDDEN_FIELDS = frozenset(
    {
        "future_return",
        "candidate_score",
        "rank_score",
        "portfolio_weight",
        "trade_decision",
        "buy_sell_signal",
        "realized_pnl",
        "target",
        "holdout_label",
    }
)


def find_forbidden_fields(value: object, path: str = "$") -> tuple[str, ...]:
    findings: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if key_text in FORBIDDEN_FIELDS:
                findings.append(child_path)
            findings.extend(find_forbidden_fields(child, child_path))
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        for index, child in enumerate(value):
            findings.extend(find_forbidden_fields(child, f"{path}[{index}]"))
    return tuple(findings)


def reject_forbidden_fields(value: object, *, module_id: str) -> None:
    findings = find_forbidden_fields(value)
    if findings:
        raise ForbiddenFieldError(
            module_id=module_id,
            code=f"{module_id.replace('.', '_')}_FORBIDDEN_FIELD",
            message="Forbidden fields were detected",
            details={"paths": findings},
        )
