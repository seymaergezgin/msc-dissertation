"""
Unit tests for the Phase 4 multi-agent orchestrator.

All tests use mocked agents (unittest.mock.MagicMock) — no real LLM calls,
no Ollama, no ChromaDB. Tests verify:
  - The orchestrator constructs all three agents when none are injected
  - Keyword routing sends each query type to the correct agent
  - The maritime-context gap (Q017-type query) routes to Risk Explainer
    with the "maritime" collection override
  - Ambiguous queries fall back gracefully to Risk Explainer, low confidence
  - The returned dict always has the required keys
  - Routing history is recorded across multiple calls
  - Every answer() call logs the full interaction via log_interaction()
    (Phase 6) — log_interaction itself is mocked (autouse), so no real
    file I/O happens in this test file
"""

import pytest
from unittest.mock import MagicMock, patch

from src.orchestrator import Orchestrator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_mock_agent(name: str, collection: str = "mock_collection") -> MagicMock:
    """Build a mocked agent whose answer() echoes a minimal valid response dict."""
    agent = MagicMock()
    agent.name = name
    agent.collection = collection
    agent.answer.return_value = {
        "answer": f"Mock answer from {name}.",
        "sources": [],
        "query": "placeholder",
        "agent": name,
    }
    agent.get_info.return_value = {"name": name, "collection": "mock", "system_prompt_preview": "..."}
    # Phase 6: Orchestrator.answer() reads these to compute per-call cost and
    # log provider/model — a bare MagicMock would return non-JSON-serialisable
    # sub-mocks here, which log_interaction would silently swallow (it's
    # non-fatal by design) but that would leave these fields untestable.
    agent.pipeline.tracker.current_spend = 0.0
    agent.pipeline.llm.get_provider_name.return_value = "openai"
    agent.pipeline.llm.model = "gpt-4o-mini"
    return agent


@pytest.fixture
def mock_agents() -> dict[str, MagicMock]:
    return {
        "risk_explainer": _make_mock_agent("Risk Explainer", collection="risk_metrics"),
        "hedge_advisor": _make_mock_agent("Hedge Advisor", collection="hedging"),
        "model_monitor": _make_mock_agent("Model Monitor", collection="risk_metrics"),
    }


@pytest.fixture
def orchestrator(mock_agents) -> Orchestrator:
    return Orchestrator(agents=mock_agents)


@pytest.fixture(autouse=True)
def mock_log_interaction():
    """
    Prevent every orchestrator test from writing to the real project
    interaction log (data/interaction_logs/interactions.jsonl). Autouse so
    no existing test needs to change; tests that want to assert on logging
    behaviour can request this fixture by name to get the mock.
    """
    with patch("src.orchestrator.log_interaction") as mock_log:
        yield mock_log


# ---------------------------------------------------------------------------
# Tests — Initialisation
# ---------------------------------------------------------------------------

class TestOrchestratorSetup:

    def test_accepts_injected_agents(self, mock_agents):
        """Orchestrator uses injected agents rather than constructing real ones."""
        orch = Orchestrator(agents=mock_agents)
        assert orch.agents is mock_agents

    def test_constructs_all_three_real_agents_when_none_injected(self):
        """With no injected agents, the orchestrator builds one of each real agent."""
        with patch("src.orchestrator.RiskExplainerAgent") as MockRisk, \
             patch("src.orchestrator.HedgeAdvisorAgent") as MockHedge, \
             patch("src.orchestrator.ModelMonitorAgent") as MockModel:
            MockRisk.return_value = _make_mock_agent("Risk Explainer")
            MockHedge.return_value = _make_mock_agent("Hedge Advisor")
            MockModel.return_value = _make_mock_agent("Model Monitor")

            orch = Orchestrator()

            MockRisk.assert_called_once()
            MockHedge.assert_called_once()
            MockModel.assert_called_once()
            assert set(orch.agents.keys()) == {"risk_explainer", "hedge_advisor", "model_monitor"}

    def test_history_starts_empty(self, orchestrator):
        """Routing history is empty before any query is answered."""
        assert orchestrator.get_routing_history() == []

    def test_get_agent_info_returns_all_three(self, orchestrator):
        """get_agent_info() returns metadata for all registered agents, no LLM calls."""
        info = orchestrator.get_agent_info()
        names = {i["name"] for i in info}
        assert names == {"Risk Explainer", "Hedge Advisor", "Model Monitor"}


# ---------------------------------------------------------------------------
# Tests — Routing: Risk Explainer keywords
# ---------------------------------------------------------------------------

class TestRiskExplainerRouting:

    def test_var_keyword_routes_to_risk_explainer(self, orchestrator):
        decision = orchestrator.route("What is our current portfolio VaR at 95% confidence?")
        assert decision["agent_key"] == "risk_explainer"
        assert decision["collection_override"] is None

    def test_cvar_keyword_routes_to_risk_explainer(self, orchestrator):
        decision = orchestrator.route("What is the CVaR for our total fleet?")
        assert decision["agent_key"] == "risk_explainer"

    def test_exposure_keyword_routes_to_risk_explainer(self, orchestrator):
        decision = orchestrator.route("What is our fuel price exposure?")
        assert decision["agent_key"] == "risk_explainer"

    def test_var_query_confidence_is_high(self, orchestrator):
        decision = orchestrator.route("What is our VaR?")
        assert decision["confidence"] == "high"


# ---------------------------------------------------------------------------
# Tests — Routing: Hedge Advisor keywords
# ---------------------------------------------------------------------------

class TestHedgeAdvisorRouting:

    def test_hedge_keyword_routes_to_hedge_advisor(self, orchestrator):
        decision = orchestrator.route("Is our current hedge ratio of 48% sufficient?")
        assert decision["agent_key"] == "hedge_advisor"

    def test_unhedged_keyword_routes_to_hedge_advisor(self, orchestrator):
        decision = orchestrator.route("How much of our fuel cost is currently unhedged across the fleet?")
        assert decision["agent_key"] == "hedge_advisor"

    def test_futures_keyword_routes_to_hedge_advisor(self, orchestrator):
        decision = orchestrator.route("Should we use futures contracts to hedge fuel costs?")
        assert decision["agent_key"] == "hedge_advisor"


# ---------------------------------------------------------------------------
# Tests — Routing: Model Monitor keywords
# ---------------------------------------------------------------------------

class TestModelMonitorRouting:

    def test_drift_keyword_routes_to_model_monitor(self, orchestrator):
        decision = orchestrator.route("Is there any sign of model drift in our VaR calculation?")
        assert decision["agent_key"] == "model_monitor"

    def test_recalibrate_keyword_routes_to_model_monitor(self, orchestrator):
        decision = orchestrator.route("When should we recalibrate the volatility model?")
        assert decision["agent_key"] == "model_monitor"

    def test_correlation_keyword_routes_to_model_monitor(self, orchestrator):
        decision = orchestrator.route("Is our correlation assumption still valid?")
        assert decision["agent_key"] == "model_monitor"


# ---------------------------------------------------------------------------
# Tests — Routing: Maritime context gap (Section 11, Finding 3)
# ---------------------------------------------------------------------------

class TestMaritimeContextRouting:

    def test_hsfo_query_routes_to_risk_explainer(self, orchestrator):
        """Q017-type query: HSFO/VLSFO — must route to Risk Explainer, not fail silently."""
        decision = orchestrator.route("Why does MV Iron Maiden use HSFO instead of VLSFO?")
        assert decision["agent_key"] == "risk_explainer"

    def test_hsfo_query_triggers_maritime_collection_override(self, orchestrator):
        """This is the critical Phase 3 gap fix: maritime queries must use the maritime collection."""
        decision = orchestrator.route("Why does MV Iron Maiden use HSFO instead of VLSFO?")
        assert decision["collection_override"] == "maritime"

    def test_imo_keyword_triggers_maritime_override(self, orchestrator):
        decision = orchestrator.route("How does the IMO 2020 sulphur cap affect our fleet?")
        assert decision["collection_override"] == "maritime"

    def test_scrubber_keyword_triggers_maritime_override(self, orchestrator):
        decision = orchestrator.route("Should we install scrubbers on our VLCC?")
        assert decision["collection_override"] == "maritime"

    def test_strong_maritime_keyword_overrides_even_with_competing_category(self, orchestrator):
        """A strong maritime term (hsfo) must win even when 'hedge' also appears."""
        decision = orchestrator.route("Should we hedge our HSFO exposure given IMO rules?")
        assert decision["collection_override"] == "maritime"
        assert decision["agent_key"] == "risk_explainer"

    def test_maritime_query_calls_agent_with_collection_override_kwarg(self, orchestrator, mock_agents):
        """The orchestrator must actually pass collection_override='maritime' to the agent call."""
        orchestrator.answer("Why does MV Iron Maiden use HSFO instead of VLSFO?")
        mock_agents["risk_explainer"].answer.assert_called_once_with(
            "Why does MV Iron Maiden use HSFO instead of VLSFO?", collection_override="maritime"
        )

    def test_non_maritime_query_does_not_pass_collection_override(self, orchestrator, mock_agents):
        """A plain VaR question must NOT pass a collection_override kwarg."""
        orchestrator.answer("What is our current VaR?")
        mock_agents["risk_explainer"].answer.assert_called_once_with("What is our current VaR?")


class TestRegulatoryWeakKeywordRouting:
    """
    Regression tests for the finding that "regulatory" alone is too generic
    to safely trigger the maritime override (see PROJECT_DOC_v0.4.md Section 9):
    a Model Monitor question about regulatory reporting standards should NOT
    be hijacked into the maritime collection just because it contains the
    word "regulatory".
    """

    def test_regulatory_alone_triggers_maritime_when_nothing_else_matches(self, orchestrator):
        """With no competing category, 'regulatory' alone is still a usable signal."""
        decision = orchestrator.route("What are the regulatory requirements for our fleet?")
        assert decision["collection_override"] == "maritime"
        assert decision["confidence"] == "medium"

    def test_regulatory_does_not_override_a_clear_model_monitor_match(self, orchestrator):
        """The core fix: 'regulatory' must not hijack a clear Model Monitor question."""
        decision = orchestrator.route(
            "What regulatory reporting standard should our risk model follow?"
        )
        assert decision["collection_override"] is None
        assert decision["agent_key"] == "model_monitor"

    def test_regulatory_does_not_override_a_clear_hedge_advisor_match(self, orchestrator):
        """Same fix, verified against the Hedge Advisor category."""
        decision = orchestrator.route(
            "Are there regulatory constraints on the futures we use to hedge?"
        )
        assert decision["collection_override"] is None
        assert decision["agent_key"] == "hedge_advisor"


# ---------------------------------------------------------------------------
# Tests — Ambiguous / fallback routing
# ---------------------------------------------------------------------------

class TestFallbackRouting:

    def test_ambiguous_query_falls_back_to_risk_explainer(self, orchestrator):
        decision = orchestrator.route("Tell me something interesting about our fleet.")
        assert decision["agent_key"] == "risk_explainer"

    def test_ambiguous_query_confidence_is_low(self, orchestrator):
        decision = orchestrator.route("Tell me something interesting about our fleet.")
        assert decision["confidence"] == "low"

    def test_ambiguous_query_routing_reason_explains_default(self, orchestrator):
        decision = orchestrator.route("Tell me something interesting about our fleet.")
        assert "default" in decision["routing_reason"].lower()


# ---------------------------------------------------------------------------
# Tests — answer() response structure
# ---------------------------------------------------------------------------

class TestOrchestratorAnswer:

    def test_answer_returns_dict(self, orchestrator):
        result = orchestrator.answer("What is our VaR?")
        assert isinstance(result, dict)

    def test_answer_contains_required_orchestrator_keys(self, orchestrator):
        result = orchestrator.answer("What is our VaR?")
        required_keys = {"answer", "sources", "agent", "query", "routed_to", "routing_reason", "confidence"}
        assert required_keys.issubset(result.keys())

    def test_routed_to_matches_agent_name(self, orchestrator):
        result = orchestrator.answer("Is our hedge ratio sufficient?")
        assert result["routed_to"] == "Hedge Advisor"

    def test_confidence_is_valid_value(self, orchestrator):
        result = orchestrator.answer("What is our VaR?")
        assert result["confidence"] in ("high", "medium", "low")

    def test_original_answer_content_preserved(self, orchestrator):
        """The underlying agent's answer text passes through unchanged."""
        result = orchestrator.answer("What is our VaR?")
        assert result["answer"] == "Mock answer from Risk Explainer."


# ---------------------------------------------------------------------------
# Tests — Phase 6 interaction logging
# ---------------------------------------------------------------------------

class TestInteractionLogging:
    """
    Verifies every Orchestrator.answer() call logs the full interaction via
    src.interaction_logger.log_interaction() (see PROJECT_DOC_v0.6.md).
    log_interaction itself is mocked (mock_log_interaction, autouse) so these
    tests never touch the real filesystem.
    """

    def test_log_interaction_called_once_per_answer(self, orchestrator, mock_log_interaction):
        orchestrator.answer("What is our VaR?")
        mock_log_interaction.assert_called_once()

    def test_logged_query_and_answer_match(self, orchestrator, mock_log_interaction):
        orchestrator.answer("What is our VaR?")
        call_kwargs = mock_log_interaction.call_args.kwargs
        assert call_kwargs["query"] == "What is our VaR?"
        assert call_kwargs["answer"] == "Mock answer from Risk Explainer."

    def test_logged_routing_fields_match_the_decision(self, orchestrator, mock_log_interaction):
        orchestrator.answer("Is our hedge ratio sufficient?")
        call_kwargs = mock_log_interaction.call_args.kwargs
        assert call_kwargs["agent"] == "Hedge Advisor"
        assert call_kwargs["routed_to"] == "Hedge Advisor"
        assert call_kwargs["confidence"] == "high"

    def test_logged_collection_is_maritime_override_when_applicable(self, orchestrator, mock_log_interaction):
        orchestrator.answer("Why does MV Iron Maiden use HSFO instead of VLSFO?")
        call_kwargs = mock_log_interaction.call_args.kwargs
        assert call_kwargs["collection"] == "maritime"

    def test_logged_collection_is_agents_own_collection_otherwise(self, orchestrator, mock_log_interaction):
        orchestrator.answer("Is our hedge ratio sufficient?")
        call_kwargs = mock_log_interaction.call_args.kwargs
        assert call_kwargs["collection"] == "hedging"

    def test_logged_provider_and_model_come_from_agents_pipeline(self, orchestrator, mock_log_interaction):
        orchestrator.answer("What is our VaR?")
        call_kwargs = mock_log_interaction.call_args.kwargs
        assert call_kwargs["provider"] == "openai"
        assert call_kwargs["model"] == "gpt-4o-mini"

    def test_eval_metadata_passed_through_when_provided(self, orchestrator, mock_log_interaction):
        orchestrator.answer("What is our VaR?", eval_metadata={"query_id": "Q001", "mode": "orchestrator"})
        call_kwargs = mock_log_interaction.call_args.kwargs
        assert call_kwargs["eval_metadata"] == {"query_id": "Q001", "mode": "orchestrator"}

    def test_eval_metadata_defaults_to_none(self, orchestrator, mock_log_interaction):
        orchestrator.answer("What is our VaR?")
        call_kwargs = mock_log_interaction.call_args.kwargs
        assert call_kwargs["eval_metadata"] is None

    def test_cost_of_call_is_zero_when_tracker_spend_unchanged(self, orchestrator, mock_log_interaction):
        """Mock agents' pipeline.tracker.current_spend never changes, so the delta must be exactly 0.0."""
        orchestrator.answer("What is our VaR?")
        call_kwargs = mock_log_interaction.call_args.kwargs
        assert call_kwargs["cost_usd"] == 0.0


# ---------------------------------------------------------------------------
# Tests — Routing history
# ---------------------------------------------------------------------------

class TestRoutingHistory:

    def test_history_records_one_entry_per_call(self, orchestrator):
        orchestrator.answer("What is our VaR?")
        assert len(orchestrator.get_routing_history()) == 1

    def test_history_accumulates_across_multiple_queries(self, orchestrator):
        orchestrator.answer("What is our VaR?")
        orchestrator.answer("Is our hedge ratio sufficient?")
        orchestrator.answer("Is there model drift?")
        history = orchestrator.get_routing_history()
        assert len(history) == 3
        assert [h["routed_to"] for h in history] == ["Risk Explainer", "Hedge Advisor", "Model Monitor"]

    def test_history_entry_contains_query_and_confidence(self, orchestrator):
        orchestrator.answer("What is our VaR?")
        entry = orchestrator.get_routing_history()[0]
        assert entry["query"] == "What is our VaR?"
        assert "confidence" in entry
        assert "timestamp" in entry


# ---------------------------------------------------------------------------
# Tests — Tie-break behaviour
# ---------------------------------------------------------------------------

class TestTieBreakRouting:

    def test_tie_between_categories_resolved_by_priority_order(self, orchestrator):
        """
        'hedge' (Hedge Advisor, 1 hit) vs 'var' (Risk Explainer, 1 hit) tie ->
        Risk Explainer wins because it is first in PRIORITY_ORDER, matching
        the top-to-bottom order of the Section 10 routing table.
        """
        decision = orchestrator.route("How does our VaR relate to our hedge position?")
        assert decision["agent_key"] == "risk_explainer"
        assert decision["confidence"] == "medium"
