from __future__ import annotations

from typing import Any, Mapping

from ..errors import BoundaryContractError, BoundaryErrorCode

FORBIDDEN_FIELDS = frozenset({
    "target", "future_return", "label", "prediction", "signal_direction", "buy_sell_signal",
    "candidate_id", "candidate_score", "rank_score", "portfolio_weight", "trade_decision",
    "realized_pnl", "execution_fill", "position_size", "feature_genome", "mutation_candidate",
    "promotion_decision",
})
PRIVATE_FIELDS = frozenset({
    "content", "memory_text", "message_text", "prompt", "raw_payload", "tool_payload",
    "private_notes", "credentials", "api_key",
})
HIDDEN_BUNDLE_FIELDS = frozenset({"records", "rows", "items", "sources", "snapshots", "documents", "quotes"})


def scan_fields(value: Any, *, private: bool = False, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            text = str(key)
            if text in FORBIDDEN_FIELDS:
                raise BoundaryContractError(
                    BoundaryErrorCode.FORBIDDEN_FIELD, f"forbidden field {text!r}", path=f"{path}.{text}"
                )
            if private and text in PRIVATE_FIELDS:
                raise BoundaryContractError(
                    BoundaryErrorCode.PRIVATE_FIELD, f"private field {text!r}", path=f"{path}.{text}"
                )
            scan_fields(child, private=private, path=f"{path}.{text}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            scan_fields(child, private=private, path=f"{path}[{index}]")


def assert_reference_only_manifest(value: Any, path: str = "manifest") -> None:
    if isinstance(value, Mapping):
        leaked = HIDDEN_BUNDLE_FIELDS.intersection(value)
        if leaked:
            raise BoundaryContractError(
                BoundaryErrorCode.HIDDEN_BUNDLE,
                f"hidden payload keys detected: {sorted(leaked)}",
                path=path,
            )
        for key, child in value.items():
            assert_reference_only_manifest(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            assert_reference_only_manifest(child, f"{path}[{index}]")
