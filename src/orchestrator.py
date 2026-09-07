"""
Multi-agent orchestrator (Phase 4 supervisor).

Routes an incoming natural-language query to the specialist agent best
equipped to answer it — Risk Explainer, Hedge Advisor, or Model Monitor —
and returns that agent's response augmented with routing metadata.

Design intent (deliberately simple — see PROJECT_DOC_v0.4.md Section 3.3 for
the full rationale): a keyword classifier over the routing table below,
plus one special case for the maritime-context gap found in Phase 3
testing. This is intentionally NOT a LangGraph StateGraph on the first
pass — Phase 3's own findings warned against overengineering a routing
layer before a simple approach has been shown to be insufficient. If a
future evaluation phase shows keyword routing misclassifying too often,
a semantic/embedding-based classifier is the natural next step.

Routing table (Section 10 of the Phase 4 brief):
  VaR, CVaR, exposure, volatility, methodology       -> Risk Explainer
  hedge, hedging, hedge ratio, futures, swap, unhedged -> Hedge Advisor
  model, drift, recalibrate, assumption, correlation,
    historical window                                -> Model Monitor
  IMO, sulphur, scrubber, HSFO, VLSFO, Stopford        -> Risk Explainer,
    (STRONG maritime keywords — always override)         but retrieve from
                                                          the "maritime"
                                                          ChromaDB collection
  regulatory                                          -> same maritime
    (WEAK maritime keyword — only overrides when          override, but ONLY
     no other category also matched; otherwise the         when no other
     other category's match wins, since "regulatory"        category also
     alone is too generic to safely override a clear         matched (see
     Risk/Hedge/Model match — e.g. "what regulatory           Decision 15)
     reporting standard should our VaR model follow?"
     is a Model Monitor question, not a maritime one)
  (no keyword match)                                  -> Risk Explainer,
                                                          confidence "low"

The maritime case exists to fix the single most important gap found in
Phase 3 comparative testing (Q017): "Why does MV Iron Maiden use HSFO?"
retrieved nothing useful because "scrubber" and "IMO 2020" live in the
"maritime" ChromaDB collection, not "risk_metrics". Rather than duplicating
the Risk Explainer's RAG+ prompt-assembly logic here, the orchestrator
calls RiskExplainerAgent.answer(query, collection_override="maritime") —
same persona and portfolio injection, different retrieval source.

Conversation state: kept deliberately minimal. Each call to answer() is
appended to self.history as a flat log entry (query, routed agent,
confidence, timestamp) for dissertation evidence and debugging — not a
context-carrying multi-turn memory. Building pronoun resolution or
follow-up-question context was judged out of scope for Phase 4 (see
Section 18: "do not add features not required by Phase 4"). Note this
in-memory history is distinct from the persistent interaction log below
(Phase 6) — see PROJECT_DOC_v0.6.md Decision 18 for why they're separate.

Interaction logging (Phase 6): every call to answer() is also persisted
to data/interaction_logs/interactions.jsonl via
src.interaction_logger.log_interaction() — full query, full answer,
routing decision, sources, timing, provider/model, and per-call cost.
This is the durable record used for dissertation evidence, supervisor
review, and Phase 6 evaluation scoring; self.history above is only an
in-memory summary for the lifetime of one Orchestrator instance.

Usage:
    from src.orchestrator import Orchestrator

    orchestrator = Orchestrator()
    result = orchestrator.answer("Why does MV Iron Maiden use HSFO instead of VLSFO?")
    print(result["routed_to"])       # "Risk Explainer"
    print(result["routing_reason"])  # explains the maritime override
    print(result["confidence"])      # "high" / "medium" / "low"
    print(result["answer"])          # the agent's plain-English response
"""

import logging
import time
from typing import Optional

from agents.base_agent import BaseAgent
from agents.hedge_advisor import HedgeAdvisorAgent
from agents.model_monitor import ModelMonitorAgent
from agents.risk_explainer import RiskExplainerAgent
from src.interaction_logger import log_interaction

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Routes queries to the appropriate specialist agent and returns its answer.

    How it works:
    1. On init: creates (or accepts, for testing) the three specialist agents.
    2. route(): scores the query's keywords against each agent's routing table
       and returns which agent should handle it, why, and how confident that
       decision is.
    3. answer(): calls route(), invokes the chosen agent, and merges routing
       metadata ("routed_to", "routing_reason", "confidence") into the
       agent's own response dict.

    Args:
        agents: Optional dict mapping "risk_explainer" / "hedge_advisor" /
                "model_monitor" to pre-built agent instances. Tests inject
                mocks here; production code leaves this None so real agents
                (and their real RAGPipeline / ChromaDB connections) are built.
    """

    # Keyword sets — see module docstring for the routing table this implements.
    RISK_EXPLAINER_KEYWORDS = ["var", "cvar", "value at risk", "exposure", "volatility", "methodology"]
    HEDGE_ADVISOR_KEYWORDS = ["hedge", "hedging", "hedge ratio", "futures", "swap", "unhedged"]
    MODEL_MONITOR_KEYWORDS = ["model", "drift", "recalibrate", "recalibration", "assumption", "correlation", "historical window"]

    # Maritime keywords are split into "strong" (unambiguous maritime/regulatory
    # terms — always trigger the collection override) and "weak" ("regulatory"
    # alone is too generic: a Model Monitor question like "what regulatory
    # reporting standard should our VaR model follow?" would otherwise be
    # hijacked into the maritime collection). See PROJECT_DOC_v0.4.md Section 9
    # for the finding this fixes.
    MARITIME_STRONG_KEYWORDS = ["imo", "imo 2020", "sulphur", "sulfur", "scrubber", "hsfo", "vlsfo", "stopford"]
    MARITIME_WEAK_KEYWORDS = ["regulatory"]

    # Tie-break order when two categories match the same number of keywords —
    # mirrors the top-to-bottom order of the Section 10 routing table.
    PRIORITY_ORDER = ["risk_explainer", "hedge_advisor", "model_monitor"]

    def __init__(self, agents: Optional[dict[str, BaseAgent]] = None) -> None:
        self.agents: dict[str, BaseAgent] = agents or {
            "risk_explainer": RiskExplainerAgent(),
            "hedge_advisor": HedgeAdvisorAgent(),
            "model_monitor": ModelMonitorAgent(),
        }
        self.history: list[dict] = []
        logger.info("Orchestrator initialised with %d agents", len(self.agents))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def route(self, query: str) -> dict:
        """
        Decide which agent should handle a query, without calling it.

        Step by step:
        1. Lower-case the query and check for STRONG maritime keywords first
           — this case takes priority because it changes *how* the winning
           agent is invoked (collection override), not just *which* agent
           wins, and it is the critical gap Phase 4 must fix.
        2. If only the WEAK maritime keyword ("regulatory") matched, don't
           immediately override: check whether any other category also
           matched. If another category matched, that is very likely the
           correct routing (e.g. "regulatory reporting for our VaR model" is
           a Model Monitor question, not a maritime one) — fall through to
           normal category scoring. If nothing else matched, "regulatory"
           is the only signal available, so honour it as a (medium-confidence)
           maritime override.
        3. If no maritime keywords matched at all, score the query against
           the Risk Explainer, Hedge Advisor, and Model Monitor keyword sets.
        4. If no keyword matched any category, fall back to Risk Explainer
           with confidence "low" (Section 10: "Ambiguous -> default").
        5. Otherwise pick the category with the most keyword hits; ties are
           broken using PRIORITY_ORDER. Confidence is "high" when exactly
           one category wins outright, "medium" when a tie was broken.

        Args:
            query: The user's natural language question.

        Returns:
            Dict with keys:
              - "agent_key" (str): one of "risk_explainer", "hedge_advisor",
                "model_monitor"
              - "collection_override" (Optional[str]): "maritime" when the
                maritime case matched, otherwise None
              - "routing_reason" (str): human-readable explanation, logged
                and returned to the caller as dissertation evidence
              - "confidence" (str): "high", "medium", or "low"
        """
        query_lower = query.lower()

        strong_maritime_hits = self._match_keywords(query_lower, self.MARITIME_STRONG_KEYWORDS)
        weak_maritime_hits = self._match_keywords(query_lower, self.MARITIME_WEAK_KEYWORDS)

        scores = {
            "risk_explainer": self._match_keywords(query_lower, self.RISK_EXPLAINER_KEYWORDS),
            "hedge_advisor": self._match_keywords(query_lower, self.HEDGE_ADVISOR_KEYWORDS),
            "model_monitor": self._match_keywords(query_lower, self.MODEL_MONITOR_KEYWORDS),
        }
        nonzero = {k: v for k, v in scores.items() if v}

        if strong_maritime_hits:
            # Unambiguous maritime signal — always wins, regardless of what else matched.
            all_maritime_hits = strong_maritime_hits + weak_maritime_hits
            confidence = "high" if not nonzero else "medium"
            return {
                "agent_key": "risk_explainer",
                "collection_override": "maritime",
                "routing_reason": (
                    f"Matched maritime/regulatory keyword(s) {all_maritime_hits} — routed to "
                    "Risk Explainer with the 'maritime' collection override "
                    "(fixes the Phase 3 Q017 gap: risk_metrics collection lacks IMO/scrubber content)"
                ),
                "confidence": confidence,
            }

        if weak_maritime_hits and not nonzero:
            # Only "regulatory" (or similar generic term) matched, and no other
            # category has a competing signal — safe to treat as maritime, but
            # confidence reflects that the signal is weaker than a strong term.
            return {
                "agent_key": "risk_explainer",
                "collection_override": "maritime",
                "routing_reason": (
                    f"Matched maritime/regulatory keyword(s) {weak_maritime_hits} — routed to "
                    "Risk Explainer with the 'maritime' collection override "
                    "(fixes the Phase 3 Q017 gap: risk_metrics collection lacks IMO/scrubber content)"
                ),
                "confidence": "medium",
            }

        # Either no maritime keyword matched, or only the weak "regulatory" term
        # matched while another category also matched — in the latter case the
        # other category is very likely the correct routing (e.g. a Model Monitor
        # question about regulatory reporting standards), so "regulatory" is
        # deliberately ignored here rather than hijacking the routing decision.

        if not nonzero:
            return {
                "agent_key": "risk_explainer",
                "collection_override": None,
                "routing_reason": "No routing keyword matched any agent — defaulting to Risk Explainer",
                "confidence": "low",
            }

        max_hits = max(len(v) for v in nonzero.values())
        winners = [k for k in self.PRIORITY_ORDER if k in nonzero and len(nonzero[k]) == max_hits]
        winner = winners[0]

        reason = f"Matched keyword(s) {nonzero[winner]} -> routed to {self._agent_label(winner)}"
        confidence = "high"
        if len(winners) > 1:
            confidence = "medium"
            reason += f" (tied with {winners[1:]}, resolved by routing-table priority order)"

        return {
            "agent_key": winner,
            "collection_override": None,
            "routing_reason": reason,
            "confidence": confidence,
        }

    def answer(self, query: str, eval_metadata: Optional[dict] = None) -> dict:
        """
        Route a query to the appropriate agent and return its answer.

        The returned dict is the agent's own response dict (answer, sources,
        agent, query, ...) with three routing keys merged in: "routed_to",
        "routing_reason", "confidence".

        Every call is also persisted via src.interaction_logger.log_interaction()
        (Phase 6) — this is the single place live UI queries (ui/app.py always
        calls Orchestrator.answer()) and Phase 6's routing-accuracy evaluation
        run get logged. The per-call cost is computed as the delta in the
        agent's own CostTracker.current_spend before/after the call, since
        individual agents don't return their call's cost directly.

        Args:
            query: The user's natural language question.
            eval_metadata: Optional dict attached to the logged interaction —
                used by evaluation/run_evaluation.py to tag a call with its
                query_id/category/difficulty/expected_agent from the 25-query
                evaluation set. None for ordinary (non-evaluation) usage.

        Returns:
            Dict with all keys the underlying agent returns, plus:
              - "routed_to" (str): the agent's name, e.g. "Risk Explainer"
              - "routing_reason" (str): why that agent was chosen
              - "confidence" (str): "high" / "medium" / "low"
        """
        start_time = time.time()
        decision = self.route(query)
        agent = self.agents[decision["agent_key"]]

        cost_before = agent.pipeline.tracker.current_spend
        if decision["collection_override"]:
            result = agent.answer(query, collection_override=decision["collection_override"])
        else:
            result = agent.answer(query)
        cost_of_call = agent.pipeline.tracker.current_spend - cost_before

        result["routed_to"] = agent.name
        result["routing_reason"] = decision["routing_reason"]
        result["confidence"] = decision["confidence"]

        self.history.append({
            "query": query,
            "routed_to": agent.name,
            "confidence": decision["confidence"],
            "timestamp": time.time(),
        })

        collection_used = decision["collection_override"] or agent.collection
        log_interaction(
            query=query,
            answer=result.get("answer", ""),
            agent=agent.name,
            routed_to=result["routed_to"],
            routing_reason=result["routing_reason"],
            confidence=result["confidence"],
            collection=collection_used,
            sources=result.get("sources"),
            retrieval_count=result.get("retrieval_count"),
            response_time_s=result.get("response_time_s"),
            provider=agent.pipeline.llm.get_provider_name(),
            model=agent.pipeline.llm.model,
            cost_usd=cost_of_call,
            eval_metadata=eval_metadata,
        )

        logger.info(
            "Orchestrator: '%s...' -> %s (confidence=%s) in %.2fs",
            query[:50], agent.name, decision["confidence"], time.time() - start_time,
        )

        return result

    def get_agent_info(self) -> list[dict]:
        """Return metadata for all registered agents, without calling any LLM."""
        return [agent.get_info() for agent in self.agents.values()]

    def get_routing_history(self) -> list[dict]:
        """Return the flat log of past routing decisions (see module docstring)."""
        return list(self.history)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _match_keywords(self, query_lower: str, keywords: list[str]) -> list[str]:
        """Return the subset of keywords that appear as substrings of the query."""
        return [kw for kw in keywords if kw in query_lower]

    def _agent_label(self, agent_key: str) -> str:
        """Human-readable agent name for routing_reason messages."""
        return self.agents[agent_key].name
