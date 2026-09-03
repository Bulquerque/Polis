from quant_pipeline.phase_03_agents_rag_memory.evaluation.ablation import (
    EvaluationObservation,
    Variant,
    evaluate_ablation,
)


def observations() -> tuple[EvaluationObservation, ...]:
    rows = []
    offsets = {
        Variant.SEARCH_RAG: 0.0000,
        Variant.SINGLE_AGENT: 0.0001,
        Variant.SOCIETY_NO_RELATIONS: 0.0002,
        Variant.SOCIETY_NO_MEMORY: 0.0003,
        Variant.SOCIETY_NO_TOOLS: 0.0004,
        Variant.FULL_SOCIETY: 0.0015,
    }
    for fold in range(5):
        for seed in range(3):
            base = tuple(((-1) ** index) * 0.001 + 0.0002 * index for index in range(8))
            for variant, offset in offsets.items():
                rows.append(
                    EvaluationObservation(
                        variant=variant,
                        fold_id=f"fold-{fold}",
                        seed=seed,
                        returns=tuple(value + offset for value in base),
                        latency_ms=10.0,
                        cost_units=1.0,
                        pit_integrity=True,
                        authority_integrity=True,
                        evidence_coverage=1.0,
                    )
                )
    return tuple(rows)


def test_ablation_statistics_are_deterministic_and_guarded() -> None:
    first = evaluate_ablation(observations())
    second = evaluate_ablation(observations())
    assert first == second
    assert first.guardrails_passed
    assert first.promotion_authority == "P0_P9_EXTERNAL_ONLY"
    assert first.production_promotion_allowed is False
    assert {item.variant for item in first.metrics} == set(Variant)
    assert len(first.comparisons) == 5


def test_guardrail_failure_blocks_value_claim() -> None:
    rows = list(observations())
    rows[0] = rows[0].model_copy(update={"pit_integrity": False})
    report = evaluate_ablation(rows)
    assert not report.guardrails_passed
    assert "GUARDRAIL_FAILURE" in report.reason_codes
