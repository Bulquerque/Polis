from __future__ import annotations

from typing import Any

from .adapters import PortableGraphQueryPort, RegexTokenizer
from .core import (
    InMemoryPort,
    assemble_context,
    build_queries,
    rerank,
    retrieve_experiences,
    retrieve_graph,
    retrieve_hybrid,
    validate_budget,
)
from .forbidden import reject_forbidden_fields
from .models import (
    ActivationPanel,
    BeliefPanel,
    BudgetConfig,
    CognitiveSchedule,
    ContextBundle,
    ContextLearningConfig,
    CutoffReport,
    EntitlementPanel,
    EvidenceMap,
    GraphArtifact,
    GraphConfig,
    IndexManifest,
    MemoryPolicy,
    PersonStatePanel,
    ProviderRegistry,
    QueryPanel,
    RetrievalBundle,
    RetrievalConfig,
    RetroPatch,
    RunSnapshot,
    S20Result,
    SocialGraph,
    StimulusPanel,
    ValidatedContextBundle,
)
from .ports import GraphQueryPort, KnowledgePort, MemoryPort, RerankerPort, TokenizerPort


def _config(config: dict[str, Any], key: str) -> Any:
    return config[key] if key in config else config


def run_m01(inputs: dict[str, Any]) -> QueryPanel:
    reject_forbidden_fields(inputs)
    return build_queries(
        CognitiveSchedule.model_validate(inputs["cognitive_cycle_schedule"]),
        StimulusPanel.model_validate(inputs["stimulus_panel"]),
        ActivationPanel.model_validate(inputs["activation_panel"]),
        PersonStatePanel.model_validate(inputs["current_person_state_panel"]),
        BeliefPanel.model_validate(inputs["current_belief_state_panel"]),
        RunSnapshot.model_validate(inputs["phase3_run_snapshot"]),
    )


def run_m02(
    inputs: dict[str, Any],
    config: dict[str, Any],
    *,
    memory_port: MemoryPort | None = None,
    knowledge_port: KnowledgePort | None = None,
) -> RetrievalBundle:
    reject_forbidden_fields(inputs)
    reject_forbidden_fields(config)

    queries = QueryPanel.model_validate(
        inputs["person_retrieval_query_panel"]
    )
    memory_manifest = IndexManifest.model_validate(
        inputs["memory_index_manifest"]
    )
    document_manifest = IndexManifest.model_validate(
        inputs["retrieval_index_manifest"]
    )
    MemoryPolicy.model_validate(inputs["memory_access_policy"])
    ProviderRegistry.model_validate(
        inputs["provider_adapter_registry_config"]
    )
    retrieval_config = RetrievalConfig.model_validate(
        _config(config, "retrieval_config")
    )

    memory = memory_port or InMemoryPort(
        memory_manifest.records,
        person_isolated=True,
    )
    knowledge = knowledge_port or InMemoryPort(
        document_manifest.records,
        person_isolated=False,
    )
    return retrieve_hybrid(
        queries,
        memory,
        knowledge,
        retrieval_config,
    )


def run_m03(
    inputs: dict[str, Any],
    config: dict[str, Any],
    *,
    graph_query_port: GraphQueryPort | None = None,
) -> RetrievalBundle:
    reject_forbidden_fields(inputs)
    reject_forbidden_fields(config)

    queries = QueryPanel.model_validate(
        inputs["person_retrieval_query_panel"]
    )
    graph = GraphArtifact.model_validate(inputs["graph_rag_artifact"])
    ProviderRegistry.model_validate(
        inputs["provider_adapter_registry_config"]
    )
    graph_config = GraphConfig.model_validate(
        _config(config, "graph_config")
    )
    port = graph_query_port or PortableGraphQueryPort()
    return port.query(queries, graph, graph_config, top_k=10)


def run_m04(
    inputs: dict[str, Any],
    config: dict[str, Any],
) -> RetrievalBundle:
    reject_forbidden_fields(inputs)
    reject_forbidden_fields(config)

    queries = QueryPanel.model_validate(
        inputs["person_retrieval_query_panel"]
    )
    memory = IndexManifest.model_validate(inputs["current_memory_state"])
    MemoryPolicy.model_validate(inputs["memory_access_policy"])
    learning_config = ContextLearningConfig.model_validate(
        _config(config, "context_learning_config")
    )
    retrieval_config = RetrievalConfig(
        schema_version="retrieval_config.s20.v1",
        hybrid_weights={
            "semantic": 0.4,
            "keyword": 0.2,
            "recency": 0.15,
            "importance": 0.1,
            "source_quality": 0.15,
        },
        top_k_raw=20,
        top_k_final=10,
        experience_top_k=learning_config.top_k_person_trajectories,
    )
    return retrieve_experiences(
        queries,
        memory.records,
        retrieval_config,
        learning_config,
    )


def run_m05(
    inputs: dict[str, Any],
    config: dict[str, Any],
    *,
    reranker_port: RerankerPort | None = None,
) -> tuple[RetrievalBundle, EvidenceMap]:
    reject_forbidden_fields(inputs)
    reject_forbidden_fields(config)

    bundles = (
        RetrievalBundle.model_validate(
            inputs["raw_retrieved_knowledge_bundle"]
        ),
        RetrievalBundle.model_validate(inputs["graph_retrieval_bundle"]),
        RetrievalBundle.model_validate(
            inputs["person_learning_trajectory_bundle"]
        ),
    )
    ProviderRegistry.model_validate(
        inputs["provider_adapter_registry_config"]
    )
    retrieval_config = RetrievalConfig.model_validate(
        _config(config, "retrieval_config")
    )
    return rerank(
        bundles,
        retrieval_config,
        reranker_port,
    )


def run_m06(
    inputs: dict[str, Any],
    *,
    tokenizer_port: TokenizerPort | None = None,
) -> ContextBundle:
    reject_forbidden_fields(inputs)
    tokenizer = tokenizer_port or RegexTokenizer()
    return assemble_context(
        CognitiveSchedule.model_validate(inputs["cognitive_cycle_schedule"]),
        StimulusPanel.model_validate(inputs["stimulus_panel"]),
        ActivationPanel.model_validate(inputs["activation_panel"]),
        PersonStatePanel.model_validate(inputs["current_person_state_panel"]),
        BeliefPanel.model_validate(inputs["current_belief_state_panel"]),
        RetrievalBundle.model_validate(inputs["retrieved_knowledge_bundle"]),
        SocialGraph.model_validate(inputs["current_social_graph"]),
        EntitlementPanel.model_validate(
            inputs["person_tool_entitlement_panel"]
        ),
        RetroPatch.model_validate(inputs["active_retro_policy_patch"]),
        tokenizer,
    )


def run_m07(
    inputs: dict[str, Any],
    config: dict[str, Any],
    *,
    tokenizer_port: TokenizerPort | None = None,
) -> ValidatedContextBundle:
    reject_forbidden_fields(inputs)
    reject_forbidden_fields(config)
    tokenizer = tokenizer_port or RegexTokenizer()
    return validate_budget(
        ContextBundle.model_validate(inputs["person_context_bundle"]),
        BudgetConfig.model_validate(_config(config, "context_budget_config")),
        CutoffReport.model_validate(
            inputs["model_knowledge_cutoff_report"]
        ),
        tokenizer,
    )


def run_s20(
    inputs: dict[str, Any],
    config: dict[str, Any],
    *,
    memory_port: MemoryPort | None = None,
    knowledge_port: KnowledgePort | None = None,
    reranker_port: RerankerPort | None = None,
    tokenizer_port: TokenizerPort | None = None,
) -> S20Result:
    """Run the canonical seven-module S20 capability in dependency order."""
    tokenizer = tokenizer_port or RegexTokenizer()
    queries = run_m01(inputs)

    query_input = {
        **inputs,
        "person_retrieval_query_panel": queries.model_dump(mode="json"),
    }
    raw = run_m02(
        query_input,
        config,
        memory_port=memory_port,
        knowledge_port=knowledge_port,
    )
    graph = run_m03(query_input, config)
    experiences = run_m04(query_input, config)

    rerank_input = {
        **inputs,
        "raw_retrieved_knowledge_bundle": raw.model_dump(mode="json"),
        "graph_retrieval_bundle": graph.model_dump(mode="json"),
        "person_learning_trajectory_bundle": experiences.model_dump(
            mode="json"
        ),
    }
    retrieved, evidence_map = run_m05(
        rerank_input,
        config,
        reranker_port=reranker_port,
    )

    context_input = {
        **inputs,
        "retrieved_knowledge_bundle": retrieved.model_dump(mode="json"),
    }
    context = run_m06(context_input, tokenizer_port=tokenizer)

    budget_input = {
        "person_context_bundle": context.model_dump(mode="json"),
        "model_knowledge_cutoff_report": inputs[
            "model_knowledge_cutoff_report"
        ],
    }
    validated = run_m07(
        budget_input,
        config,
        tokenizer_port=tokenizer,
    )

    return S20Result(
        person_retrieval_query_panel=queries,
        raw_retrieved_knowledge_bundle=raw,
        graph_retrieval_bundle=graph,
        person_learning_trajectory_bundle=experiences,
        retrieved_knowledge_bundle=retrieved,
        retrieval_evidence_map=evidence_map,
        person_context_bundle=context,
        validated_person_context_bundle=validated,
    )
