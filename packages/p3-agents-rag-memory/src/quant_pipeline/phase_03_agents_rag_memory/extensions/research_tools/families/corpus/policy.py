from __future__ import annotations

from collections.abc import Mapping

from .canonical import content_hash
from .models import (
    CorpusIndexReadinessReport,
    CorpusIndexSnapshot,
    CorpusInternalWorkBudget,
    CorpusMode,
    CorpusRetrievalPolicy,
    ModePolicy,
)


class CorpusRetrievalPolicyBuilder:
    MODULE_ID = "P3.S35.M02"

    def build(
        self,
        *,
        snapshot: CorpusIndexSnapshot,
        readiness: CorpusIndexReadinessReport,
        config: Mapping[str, object] | None = None,
    ) -> tuple[CorpusRetrievalPolicy, CorpusInternalWorkBudget]:
        raw = dict(config or {})
        semantic_ready = readiness.semantic_ready
        reranker_ready = readiness.reranker_ready
        modes = (
            ModePolicy(
                mode_id=CorpusMode.LOOKUP,
                max_results=self._integer(raw, "lookup_max_results", 5),
                max_internal_subqueries=1,
                max_internal_work_units=3,
                coverage_floor=0.0,
            ),
            ModePolicy(
                mode_id=CorpusMode.STANDARD,
                max_results=self._integer(raw, "standard_max_results", 15),
                max_internal_subqueries=2,
                max_internal_work_units=8,
                allow_semantic=semantic_ready,
                allow_reranker=reranker_ready,
                coverage_floor=0.25,
                downgrade_targets=(CorpusMode.LOOKUP,),
            ),
            ModePolicy(
                mode_id=CorpusMode.TRIANGULATED,
                max_results=self._integer(raw, "triangulated_max_results", 30),
                max_internal_subqueries=4,
                max_internal_work_units=20,
                allow_semantic=semantic_ready,
                allow_reranker=reranker_ready,
                minimum_source_families=2,
                require_counterevidence=True,
                coverage_floor=0.5,
                downgrade_targets=(CorpusMode.STANDARD, CorpusMode.LOOKUP),
            ),
            ModePolicy(
                mode_id=CorpusMode.FORENSIC,
                max_results=self._integer(raw, "forensic_max_results", 50),
                max_internal_subqueries=5,
                max_internal_work_units=35,
                allow_semantic=semantic_ready,
                allow_reranker=reranker_ready,
                minimum_source_families=2,
                require_counterevidence=True,
                require_version_graph=True,
                coverage_floor=0.7,
                downgrade_targets=(CorpusMode.TRIANGULATED, CorpusMode.STANDARD),
            ),
        )
        base = {
            "policy_id": f"corpus_policy_{snapshot.content_hash[:20]}",
            "snapshot_id": snapshot.snapshot_id,
            "rrf_constant": self._integer(raw, "rrf_constant", 60),
            "bm25_k1": self._float(raw, "bm25_k1", 1.5),
            "bm25_b": self._float(raw, "bm25_b", 0.75),
            "modes": modes,
        }
        policy = CorpusRetrievalPolicy(content_hash=content_hash(base), **base)
        work_base = {
            "policy_id": policy.policy_id,
            "work_units_by_mode": {
                item.mode_id: item.max_internal_work_units for item in modes
            },
            "subqueries_by_mode": {
                item.mode_id: item.max_internal_subqueries for item in modes
            },
        }
        budget = CorpusInternalWorkBudget(content_hash=content_hash(work_base), **work_base)
        return policy, budget

    @staticmethod
    def _integer(config: Mapping[str, object], key: str, default: int) -> int:
        value = config.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{key} must be an integer")
        return value

    @staticmethod
    def _float(config: Mapping[str, object], key: str, default: float) -> float:
        value = config.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise TypeError(f"{key} must be numeric")
        return float(value)
