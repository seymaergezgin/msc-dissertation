"""
Unit tests for the Risk Explainer Agent.

All tests use mocked LLM and VectorStore so no API calls or Ollama
are required. Tests verify:
  - Agent initialises correctly with and without a snapshot file
  - Portfolio context is formatted accurately from risk_metrics.json
  - answer() returns the correct dict structure
  - LLM is called with the risk_explainer system prompt
  - Portfolio figures are present in the context block sent to the LLM
  - Sources are correctly forwarded from the pipeline
  - Agent name is present in every response
  - Cost tracker is called after each response
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_RISK_METRICS = {
    "snapshot_date": "2024-11-15",
    "currency": "USD",
    "fuel_prices_per_metric_ton": {
        "VLSFO": 470.73,
        "HSFO": 385.14,
        "MGO": 545.62,
    },
    "methodology": {
        "var_method": "Variance-Covariance (Delta-Normal)",
        "confidence_levels": ["95%", "99%"],
        "time_horizon": "10 trading days",
        "volatility_basis": "Historical daily returns, recent 2-year window",
        "correlation_assumption": "Perfect positive correlation (conservative upper bound)",
    },
    "vessels": [
        {
            "vessel_name": "MV Atlantic Pioneer",
            "vessel_type": "Panamax Bulker",
            "fuel_type": "VLSFO",
            "annual_consumption_mt": 8500,
            "fuel_price_usd_per_mt": 470.73,
            "annual_fuel_cost_usd": 4001205,
            "hedge_ratio_pct": 55,
            "hedged_exposure_usd": 2200663,
            "unhedged_exposure_usd": 1800542,
            "risk_metrics": {
                "var_95_10d_usd": 43901,
                "var_99_10d_usd": 62076,
                "cvar_95_10d_usd": 56193,
                "daily_volatility_pct": 2.53,
                "annualised_volatility_pct": 40.2,
            },
        }
    ],
    "portfolio_summary": {
        "total_annual_fuel_cost_usd": 34298985,
        "total_vessels": 5,
        "portfolio_var_95_10d_usd": 376329,
        "portfolio_var_99_10d_usd": 532125,
        "portfolio_cvar_95_10d_usd": 481701,
        "average_hedge_ratio_pct": 48,
        "interpretation": "The portfolio's 10-day 95% VaR is $376,329.",
    },
}

SAMPLE_DOCS = [
    MagicMock(
        page_content="Value at Risk is the maximum loss not exceeded at a given confidence level.",
        metadata={
            "source_file": "Value_at_risk.pdf",
            "page": 1,
            "category": "risk_metrics",
        },
    )
]


def _make_mock_pipeline(answer_text: str = "Mock answer about VaR.") -> MagicMock:
    """Build a fully mocked RAGPipeline for testing."""
    pipeline = MagicMock()

    # LLM mock
    pipeline.llm.invoke.return_value = answer_text
    pipeline.llm.get_token_counts.return_value = {"input_tokens": 500, "output_tokens": 200}
    pipeline.llm.get_provider_name.return_value = "openai"
    pipeline.llm.model = "gpt-4o-mini"

    # Vector store mock
    pipeline.vs.query.return_value = SAMPLE_DOCS

    # Reuse real _format_context and _build_prompt from RAGPipeline
    from src.rag_pipeline import RAGPipeline as _Real
    real = _Real.__new__(_Real)
    pipeline._format_context = real._format_context.__func__.__get__(real, _Real)
    pipeline._format_sources = real._format_sources.__func__.__get__(real, _Real)
    pipeline._build_prompt = real._build_prompt.__func__.__get__(real, _Real)

    # Cost tracker mock
    pipeline.tracker = MagicMock()

    return pipeline


# ---------------------------------------------------------------------------
# Tests — Initialisation
# ---------------------------------------------------------------------------

class TestRiskExplainerAgentSetup:

    def test_initialises_with_correct_name(self, tmp_path):
        """Agent name attribute is 'Risk Explainer'."""
        from agents.risk_explainer import RiskExplainerAgent
        pipeline = _make_mock_pipeline()
        agent = RiskExplainerAgent(pipeline=pipeline)
        assert agent.name == "Risk Explainer"

    def test_initialises_with_correct_collection(self, tmp_path):
        """Agent always uses risk_metrics collection."""
        from agents.risk_explainer import RiskExplainerAgent
        pipeline = _make_mock_pipeline()
        agent = RiskExplainerAgent(pipeline=pipeline)
        assert agent.collection == "risk_metrics"

    def test_system_prompt_is_non_empty_string(self):
        """System prompt is a non-empty string from prompts module."""
        from agents.risk_explainer import RiskExplainerAgent
        pipeline = _make_mock_pipeline()
        agent = RiskExplainerAgent(pipeline=pipeline)
        assert isinstance(agent.system_prompt, str)
        assert len(agent.system_prompt) > 100

    def test_system_prompt_references_maritime(self):
        """System prompt instructs agent to act as a maritime risk analyst."""
        from agents.risk_explainer import RiskExplainerAgent
        agent = RiskExplainerAgent(pipeline=_make_mock_pipeline())
        assert "maritime" in agent.system_prompt.lower()

    def test_loads_risk_snapshot_when_file_exists(self, tmp_path):
        """Agent loads portfolio data when risk_metrics.json is present."""
        from agents import risk_explainer as mod
        snapshot_path = tmp_path / "risk_metrics.json"
        snapshot_path.write_text(json.dumps(SAMPLE_RISK_METRICS))
        with patch.object(mod, "RISK_METRICS_PATH", snapshot_path):
            agent = mod.RiskExplainerAgent(pipeline=_make_mock_pipeline())
            assert agent._risk_snapshot != {}
            assert agent._risk_snapshot["snapshot_date"] == "2024-11-15"

    def test_gracefully_handles_missing_snapshot(self, tmp_path):
        """Agent works without risk_metrics.json — returns knowledge-base-only answers."""
        from agents import risk_explainer as mod
        missing_path = tmp_path / "nonexistent.json"
        with patch.object(mod, "RISK_METRICS_PATH", missing_path):
            agent = mod.RiskExplainerAgent(pipeline=_make_mock_pipeline())
            assert agent._risk_snapshot == {}


# ---------------------------------------------------------------------------
# Tests — Portfolio Context Formatting
# ---------------------------------------------------------------------------

class TestPortfolioContextFormatting:

    def _agent_with_snapshot(self, tmp_path):
        from agents import risk_explainer as mod
        path = tmp_path / "risk_metrics.json"
        path.write_text(json.dumps(SAMPLE_RISK_METRICS))
        with patch.object(mod, "RISK_METRICS_PATH", path):
            return mod.RiskExplainerAgent(pipeline=_make_mock_pipeline())

    def test_portfolio_context_contains_var_figure(self, tmp_path):
        """Portfolio context block includes the VaR figure from the snapshot."""
        agent = self._agent_with_snapshot(tmp_path)
        ctx = agent._format_portfolio_as_context()
        assert "376,329" in ctx

    def test_portfolio_context_contains_cvar_figure(self, tmp_path):
        """Portfolio context block includes the CVaR figure."""
        agent = self._agent_with_snapshot(tmp_path)
        ctx = agent._format_portfolio_as_context()
        assert "481,701" in ctx

    def test_portfolio_context_contains_hedge_ratio(self, tmp_path):
        """Portfolio context block includes the average hedge ratio."""
        agent = self._agent_with_snapshot(tmp_path)
        ctx = agent._format_portfolio_as_context()
        assert "48%" in ctx

    def test_portfolio_context_contains_vessel_name(self, tmp_path):
        """Portfolio context includes vessel-level breakdown."""
        agent = self._agent_with_snapshot(tmp_path)
        ctx = agent._format_portfolio_as_context()
        assert "MV Atlantic Pioneer" in ctx

    def test_portfolio_context_contains_fuel_prices(self, tmp_path):
        """Portfolio context block includes current VLSFO/HSFO/MGO prices."""
        agent = self._agent_with_snapshot(tmp_path)
        ctx = agent._format_portfolio_as_context()
        assert "470.73" in ctx
        assert "385.14" in ctx

    def test_portfolio_context_empty_when_no_snapshot(self, tmp_path):
        """Portfolio context is empty string when snapshot file is missing."""
        from agents import risk_explainer as mod
        with patch.object(mod, "RISK_METRICS_PATH", tmp_path / "missing.json"):
            agent = mod.RiskExplainerAgent(pipeline=_make_mock_pipeline())
        assert agent._format_portfolio_as_context() == ""

    def test_portfolio_context_contains_methodology(self, tmp_path):
        """Portfolio context includes the VaR methodology name."""
        agent = self._agent_with_snapshot(tmp_path)
        ctx = agent._format_portfolio_as_context()
        assert "Variance-Covariance" in ctx


# ---------------------------------------------------------------------------
# Tests — answer() response structure
# ---------------------------------------------------------------------------

class TestRiskExplainerAgentAnswer:

    @pytest.fixture
    def agent(self, tmp_path):
        from agents import risk_explainer as mod
        path = tmp_path / "risk_metrics.json"
        path.write_text(json.dumps(SAMPLE_RISK_METRICS))
        with patch.object(mod, "RISK_METRICS_PATH", path):
            return mod.RiskExplainerAgent(pipeline=_make_mock_pipeline())

    def test_answer_returns_dict(self, agent):
        """answer() returns a dict."""
        result = agent.answer("What is our VaR?")
        assert isinstance(result, dict)

    def test_answer_contains_all_required_keys(self, agent):
        """answer() dict has all required keys."""
        result = agent.answer("What is our VaR?")
        required_keys = {"answer", "sources", "context_used", "retrieval_count",
                        "query", "agent", "portfolio_snapshot", "response_time_s"}
        assert required_keys.issubset(result.keys())

    def test_answer_key_is_non_empty_string(self, agent):
        """answer['answer'] is a non-empty string."""
        result = agent.answer("What is our VaR?")
        assert isinstance(result["answer"], str)
        assert len(result["answer"]) > 0

    def test_agent_name_in_response(self, agent):
        """answer['agent'] is 'Risk Explainer'."""
        result = agent.answer("What is our VaR?")
        assert result["agent"] == "Risk Explainer"

    def test_original_query_preserved(self, agent):
        """answer['query'] contains the original question (not augmented prompt)."""
        question = "What is our current portfolio VaR?"
        result = agent.answer(question)
        assert result["query"] == question

    def test_sources_is_list(self, agent):
        """answer['sources'] is a list."""
        result = agent.answer("What is our VaR?")
        assert isinstance(result["sources"], list)

    def test_retrieval_count_matches_sources(self, agent):
        """answer['retrieval_count'] equals the number of docs retrieved."""
        result = agent.answer("What is our VaR?")
        assert result["retrieval_count"] == len(SAMPLE_DOCS)

    def test_portfolio_snapshot_summary_in_response(self, agent):
        """answer['portfolio_snapshot'] contains key portfolio figures."""
        result = agent.answer("What is our VaR?")
        snap = result["portfolio_snapshot"]
        assert snap["portfolio_var_95_10d_usd"] == 376329
        assert snap["average_hedge_ratio_pct"] == 48
        assert snap["total_vessels"] == 5

    def test_context_contains_portfolio_data(self, agent):
        """The context block sent to the LLM includes live portfolio figures."""
        result = agent.answer("What is our VaR?")
        assert "376,329" in result["context_used"]
        assert "CURRENT PORTFOLIO DATA" in result["context_used"]

    def test_context_contains_retrieved_document(self, agent):
        """The context block also includes the retrieved document chunk."""
        result = agent.answer("What is our VaR?")
        assert "Value at Risk is the maximum loss" in result["context_used"]

    def test_llm_called_with_system_prompt(self, agent):
        """LLM is called with the Risk Explainer system prompt, not the default."""
        from prompts.system_prompts import RISK_EXPLAINER_SYSTEM_PROMPT
        agent.answer("What is our VaR?")
        call_kwargs = agent.pipeline.llm.invoke.call_args
        system_prompt_used = call_kwargs[1].get("system_prompt") or call_kwargs[0][1]
        assert system_prompt_used == RISK_EXPLAINER_SYSTEM_PROMPT

    def test_cost_tracker_called_after_answer(self, agent):
        """Cost tracker log_usage is called once per answer()."""
        agent.answer("What is our VaR?")
        agent.pipeline.tracker.log_usage.assert_called_once()

    def test_cost_tracker_query_summary_tagged(self, agent):
        """Cost log entry is tagged with [RiskAgent] prefix."""
        agent.answer("What is our VaR?")
        call_kwargs = agent.pipeline.tracker.log_usage.call_args[1]
        assert "[RiskAgent]" in call_kwargs["query_summary"]

    def test_response_time_is_positive_float(self, agent):
        """response_time_s is a positive number."""
        result = agent.answer("What is our VaR?")
        assert isinstance(result["response_time_s"], float)
        assert result["response_time_s"] >= 0

    def test_collection_override_changes_retrieval_collection(self, agent):
        """
        Phase 4: answer(query, collection_override=...) must query that
        collection instead of self.collection ("risk_metrics"). This is the
        mechanism the orchestrator uses to route maritime-context questions
        without duplicating the RAG+ prompt-assembly logic.
        """
        agent.answer("Why does MV Iron Maiden use HSFO?", collection_override="maritime")
        call_args = agent.pipeline.vs.query.call_args
        assert call_args.kwargs["collection"] == "maritime"

    def test_no_override_uses_agents_default_collection(self, agent):
        """Without collection_override, retrieval still uses self.collection."""
        agent.answer("What is our VaR?")
        call_args = agent.pipeline.vs.query.call_args
        assert call_args.kwargs["collection"] == "risk_metrics"


# ---------------------------------------------------------------------------
# Tests — BaseAgent interface
# ---------------------------------------------------------------------------

class TestBaseAgentInterface:

    def test_base_agent_cannot_be_instantiated_directly(self):
        """BaseAgent is abstract — cannot be instantiated without subclassing."""
        from agents.base_agent import BaseAgent
        with pytest.raises(TypeError):
            BaseAgent()

    def test_get_info_returns_name_and_collection(self):
        """get_info() returns agent metadata without calling the LLM."""
        from agents.risk_explainer import RiskExplainerAgent
        agent = RiskExplainerAgent(pipeline=_make_mock_pipeline())
        info = agent.get_info()
        assert info["name"] == "Risk Explainer"
        assert info["collection"] == "risk_metrics"
        assert "system_prompt_preview" in info


# ---------------------------------------------------------------------------
# Tests — prompts/risk_prompts.py
# ---------------------------------------------------------------------------

class TestEvaluationQuerySet:

    def test_query_set_has_38_queries(self):
        """Evaluation set contains exactly 38 queries (25 original + 13 added in Phase 7 to rebalance Hedge Advisor/Model Monitor coverage)."""
        from prompts.risk_prompts import RISK_EVALUATION_QUERIES
        assert len(RISK_EVALUATION_QUERIES) == 38

    def test_all_queries_have_required_fields(self):
        """Every query has id, query, category, expected_elements, expected_agent, difficulty."""
        from prompts.risk_prompts import RISK_EVALUATION_QUERIES
        for q in RISK_EVALUATION_QUERIES:
            assert "id" in q
            assert "query" in q
            assert "category" in q
            assert "expected_elements" in q
            assert "expected_agent" in q
            assert "difficulty" in q

    def test_expected_agent_is_a_known_agent_key(self):
        """expected_agent (Phase 6) must be one of the three real agent keys."""
        from prompts.risk_prompts import RISK_EVALUATION_QUERIES
        valid_agents = {"risk_explainer", "hedge_advisor", "model_monitor"}
        for q in RISK_EVALUATION_QUERIES:
            assert q["expected_agent"] in valid_agents

    def test_queries_by_expected_agent_index_covers_all_queries(self):
        """QUERIES_BY_EXPECTED_AGENT (Phase 6) partitions all queries with no loss."""
        from prompts.risk_prompts import QUERIES_BY_EXPECTED_AGENT, RISK_EVALUATION_QUERIES
        total = sum(len(v) for v in QUERIES_BY_EXPECTED_AGENT.values())
        assert total == len(RISK_EVALUATION_QUERIES)

    def test_hedge_advisor_and_model_monitor_have_comparable_coverage(self):
        """
        Phase 7 rebalancing: Hedge Advisor and Model Monitor must each have
        at least 8 queries, closing the n=3-per-domain gap an external
        dissertation review flagged as too thin to support a claim of
        validation "across all three agent domains."
        """
        from prompts.risk_prompts import QUERIES_BY_EXPECTED_AGENT
        assert len(QUERIES_BY_EXPECTED_AGENT["hedge_advisor"]) >= 8
        assert len(QUERIES_BY_EXPECTED_AGENT["model_monitor"]) >= 8

    def test_boundary_category_exists_for_routing_robustness_probes(self):
        """Phase 7: at least 2 'boundary' queries exist to probe routing beyond the two known Decision 15 cases."""
        from prompts.risk_prompts import QUERIES_BY_CATEGORY
        assert len(QUERIES_BY_CATEGORY.get("boundary", [])) >= 2

    def test_hedging_category_queries_expect_hedge_advisor(self):
        """Sanity check: the 3 'hedging' category queries should target Hedge Advisor."""
        from prompts.risk_prompts import QUERIES_BY_CATEGORY
        for q in QUERIES_BY_CATEGORY["hedging"]:
            assert q["expected_agent"] == "hedge_advisor"

    def test_methodology_category_queries_expect_model_monitor(self):
        """Sanity check: the 2 'methodology' category queries should target Model Monitor."""
        from prompts.risk_prompts import QUERIES_BY_CATEGORY
        for q in QUERIES_BY_CATEGORY["methodology"]:
            assert q["expected_agent"] == "model_monitor"

    def test_query_ids_are_unique(self):
        """No duplicate query IDs."""
        from prompts.risk_prompts import RISK_EVALUATION_QUERIES
        ids = [q["id"] for q in RISK_EVALUATION_QUERIES]
        assert len(ids) == len(set(ids))

    def test_queries_by_id_lookup_works(self):
        """QUERIES_BY_ID index contains all 38 queries."""
        from prompts.risk_prompts import QUERIES_BY_ID, RISK_EVALUATION_QUERIES
        assert len(QUERIES_BY_ID) == 38
        assert QUERIES_BY_ID["Q001"]["query"].startswith("What is our current portfolio VaR")

    def test_factual_queries_include_portfolio_var(self):
        """Q001 — factual VaR query — expects the dollar figure $376,329."""
        from prompts.risk_prompts import QUERIES_BY_ID
        q = QUERIES_BY_ID["Q001"]
        assert "$376,329" in q["expected_elements"]

    def test_summary_query_exists(self):
        """Q025 — board-level summary — is included."""
        from prompts.risk_prompts import QUERIES_BY_ID
        assert "Q025" in QUERIES_BY_ID
        assert QUERIES_BY_ID["Q025"]["category"] == "summary"
