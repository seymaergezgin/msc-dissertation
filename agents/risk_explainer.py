"""
Risk Explainer Agent.

Answers questions about the company's current fuel price risk metrics:
VaR, CVaR, exposure, volatility, hedge ratios, and scenario analysis.

Architecture — RAG+ pattern (key design contribution of this dissertation):

This agent combines TWO types of context in every response, which is
what distinguishes it from a plain RAG system:

  1. LIVE PORTFOLIO DATA — the current risk snapshot loaded from
     data/synthetic/risk_metrics.json. Provides the actual figures the
     user is asking about: portfolio VaR, vessel-level CVaR, hedge ratios.
     This data changes over time as the fleet's positions change.

  2. DOMAIN KNOWLEDGE — chunks retrieved from the ChromaDB "risk_metrics"
     collection (VaR textbook, Wikipedia VaR/CVaR articles). Explains what
     the figures mean, how they are calculated, and what good risk management
     looks like. This is the static background knowledge base.

The LLM receives both in the same prompt, so it can answer questions like:
  "Our portfolio VaR is $376,329. Is that high? What does that number mean?"
  — combining the live figure with the domain knowledge about VaR interpretation.

This pattern is documented in the dissertation as "context-augmented RAG" or
"RAG with dynamic data injection", distinguishing it from standard RAG where
only static documents are retrieved.

Usage:
    from agents.risk_explainer import RiskExplainerAgent

    agent = RiskExplainerAgent()

    result = agent.answer("What is our current VaR at 95% confidence?")
    print(result["answer"])

    # Access the portfolio snapshot used
    print(result["portfolio_snapshot"]["portfolio_var_95_10d_usd"])  # 376329

    # See sources retrieved from ChromaDB
    for source in result["sources"]:
        print(source["file"], "page", source["page"])
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

from agents.base_agent import BaseAgent
from config.settings import DATA_DIR
from prompts.system_prompts import RISK_EXPLAINER_SYSTEM_PROMPT
from src.rag_pipeline import RAGPipeline

logger = logging.getLogger(__name__)

RISK_METRICS_PATH = DATA_DIR / "synthetic" / "risk_metrics.json"


class RiskExplainerAgent(BaseAgent):
    """
    Explains maritime fuel risk metrics in plain English for business stakeholders.

    How it works:
    1. On init: loads the portfolio risk snapshot from risk_metrics.json.
    2. On answer(): retrieves the top-5 most semantically relevant chunks
       from the "risk_metrics" ChromaDB collection.
    3. Prepends the live portfolio data as "CURRENT PORTFOLIO DATA" to the
       retrieved document chunks — the LLM sees live figures first, then
       background domain knowledge.
    4. Calls the LLM with the RISK_EXPLAINER_SYSTEM_PROMPT persona.
    5. Returns the answer along with source citations and a snapshot summary.

    The portfolio data injection pattern means this agent can answer both:
      - "What is VaR?" (conceptual — answered from domain knowledge)
      - "What is OUR VaR?" (factual — answered from portfolio data)
      - "Is our VaR level acceptable?" (evaluative — needs both)

    Args:
        pipeline: Pre-initialised RAGPipeline. If None, one is created
                  using collection="risk_metrics".
    """

    name = "Risk Explainer"
    collection = "risk_metrics"

    def __init__(self, pipeline: Optional[RAGPipeline] = None) -> None:
        super().__init__(pipeline=pipeline or RAGPipeline(collection=self.collection))
        self._risk_snapshot = self._load_risk_snapshot()
        if self._risk_snapshot:
            ps = self._risk_snapshot.get("portfolio_summary", {})
            logger.info(
                "Risk snapshot loaded: %d vessels | portfolio VaR $%s (95%%, 10d)",
                len(self._risk_snapshot.get("vessels", [])),
                f"{ps.get('portfolio_var_95_10d_usd', 0):,}",
            )
        else:
            logger.warning(
                "Risk snapshot not found at %s — agent will answer from knowledge base only.",
                RISK_METRICS_PATH,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def answer(self, query: str, collection_override: Optional[str] = None) -> dict:
        """
        Answer a risk-related query using live portfolio data + RAG context.

        The prompt structure seen by the LLM:
          CONTEXT DOCUMENTS:
          [CURRENT PORTFOLIO DATA — as of 2024-11-15]
          ... vessel breakdown, VaR figures, hedge ratios ...

          ---

          [Context 1 — Value_at_risk.pdf, page 3]
          ... retrieved chunk explaining VaR ...

          ---
          [Context 2-5 — more retrieved chunks ...]

          ---

          USER QUESTION:
          <user's query>

          ---

          Please answer based on the context...

        Args:
            query: Natural language question about risk metrics.
            collection_override: If set, retrieve from this ChromaDB collection
                instead of self.collection ("risk_metrics"). Used by the Phase 4
                orchestrator for maritime-context questions (e.g. "Why does
                MV Iron Maiden use HSFO?") that need the "maritime" collection
                (Stopford, IMO MEPC70) rather than VaR methodology documents —
                the Risk Explainer persona and portfolio injection stay the
                same; only the retrieval source changes.

        Returns:
            Dict with keys:
              - "answer" (str): Plain-English response in structured format
              - "sources" (list[dict]): Retrieved chunk citations
              - "context_used" (str): Full context block shown to the LLM
              - "retrieval_count" (int): Number of chunks retrieved
              - "query" (str): Original question
              - "agent" (str): "Risk Explainer"
              - "portfolio_snapshot" (dict): Key portfolio figures summary
              - "response_time_s" (float): Time to generate the response
        """
        start_time = time.time()

        # Step 1: Retrieve relevant domain knowledge from ChromaDB
        context_docs = self.pipeline.vs.query(
            query, collection=collection_override or self.collection, k=5
        )

        # Step 2: Build combined context — portfolio data first, then retrieved docs
        # This ordering matters: the LLM reads top-to-bottom, so the live portfolio
        # figures appear before the general domain knowledge. This reduces the risk
        # of the model generalising rather than citing the specific portfolio figures.
        portfolio_context = self._format_portfolio_as_context()
        docs_context = self.pipeline._format_context(context_docs)

        if portfolio_context:
            full_context = f"{portfolio_context}\n\n---\n\n{docs_context}"
        else:
            full_context = docs_context

        # Step 3: Build the augmented prompt and call the LLM
        prompt = self.pipeline._build_prompt(query, full_context)
        answer_text = self.pipeline.llm.invoke(prompt, system_prompt=self.system_prompt)

        elapsed = time.time() - start_time

        # Step 4: Log cost (non-fatal if tracker fails)
        tokens = self.pipeline.llm.get_token_counts(prompt, answer_text)
        try:
            self.pipeline.tracker.log_usage(
                provider=self.pipeline.llm.get_provider_name(),
                model=self.pipeline.llm.model,
                input_tokens=tokens["input_tokens"],
                output_tokens=tokens["output_tokens"],
                query_summary=f"[RiskAgent] {query[:70]}",
            )
        except Exception as cost_err:
            logger.warning("Cost tracking failed (non-fatal): %s", cost_err)

        logger.info(
            "RiskExplainerAgent: '%s...' answered in %.2fs | provider: %s | %d chunks retrieved",
            query[:50], elapsed, self.pipeline.llm.get_provider_name(), len(context_docs),
        )

        return {
            "answer": answer_text,
            "sources": self.pipeline._format_sources(context_docs),
            "context_used": full_context,
            "retrieval_count": len(context_docs),
            "query": query,
            "agent": self.name,
            "portfolio_snapshot": self._get_snapshot_summary(),
            "response_time_s": round(elapsed, 2),
        }

    @property
    def system_prompt(self) -> str:
        return RISK_EXPLAINER_SYSTEM_PROMPT

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_risk_snapshot(self) -> dict:
        """
        Load the portfolio risk snapshot from the synthetic data file.

        Returns an empty dict if the file does not exist, allowing the
        agent to degrade gracefully to knowledge-base-only responses.
        """
        if not RISK_METRICS_PATH.exists():
            return {}
        with open(RISK_METRICS_PATH) as f:
            return json.load(f)

    def _format_portfolio_as_context(self) -> str:
        """
        Format the risk snapshot as a plain-text context block.

        This block is injected at the top of the context before the
        RAG-retrieved document chunks. Plain text is used rather than JSON
        because the LLM handles natural language more reliably for explanation
        tasks — JSON requires the model to parse structure before reasoning.

        The block starts with "[CURRENT PORTFOLIO DATA]" so the LLM can
        clearly attribute citations ("according to the current portfolio data").

        Returns:
            Formatted multi-line string, or empty string if no snapshot loaded.
        """
        if not self._risk_snapshot:
            return ""

        snap = self._risk_snapshot
        ps = snap.get("portfolio_summary", {})
        prices = snap.get("fuel_prices_per_metric_ton", {})
        method = snap.get("methodology", {})
        vessels = snap.get("vessels", [])

        lines = [
            f"[CURRENT PORTFOLIO DATA — snapshot date: {snap.get('snapshot_date', 'N/A')}]",
            "",
            "CURRENT FUEL PRICES (USD per metric ton):",
            f"  VLSFO (Very Low Sulphur Fuel Oil): ${prices.get('VLSFO', 'N/A')}/MT",
            f"  HSFO  (High Sulphur Fuel Oil):     ${prices.get('HSFO', 'N/A')}/MT",
            f"  MGO   (Marine Gas Oil):             ${prices.get('MGO', 'N/A')}/MT",
            "",
            "PORTFOLIO RISK SUMMARY (entire fleet, 5 vessels):",
            f"  Total annual fuel cost:                      ${ps.get('total_annual_fuel_cost_usd', 0):>15,.0f}",
            f"  Portfolio VaR  (95% confidence, 10 days):   ${ps.get('portfolio_var_95_10d_usd', 0):>15,.0f}",
            f"  Portfolio VaR  (99% confidence, 10 days):   ${ps.get('portfolio_var_99_10d_usd', 0):>15,.0f}",
            f"  Portfolio CVaR (95% confidence, 10 days):   ${ps.get('portfolio_cvar_95_10d_usd', 0):>15,.0f}",
            f"  Average hedge ratio across fleet:            {ps.get('average_hedge_ratio_pct', 0):>14}%",
            f"  Interpretation: {ps.get('interpretation', '')}",
            "",
            f"VaR METHODOLOGY: {method.get('var_method', 'N/A')}",
            f"  Confidence levels: {', '.join(method.get('confidence_levels', []))}",
            f"  Time horizon: {method.get('time_horizon', 'N/A')}",
            f"  Volatility basis: {method.get('volatility_basis', 'N/A')}",
            f"  Correlation assumption: {method.get('correlation_assumption', 'N/A')}",
            "",
            "VESSEL-LEVEL BREAKDOWN:",
        ]

        for v in vessels:
            rm = v.get("risk_metrics", {})
            lines.append(
                f"  {v['vessel_name']} | {v['vessel_type']} | Fuel: {v['fuel_type']} | "
                f"Annual cost: ${v['annual_fuel_cost_usd']:,.0f} | "
                f"Hedge: {v['hedge_ratio_pct']}% | "
                f"VaR(95%,10d): ${rm.get('var_95_10d_usd', 0):,.0f} | "
                f"CVaR(95%,10d): ${rm.get('cvar_95_10d_usd', 0):,.0f} | "
                f"Daily vol: {rm.get('daily_volatility_pct', 0)}%"
            )

        return "\n".join(lines)

    def _get_snapshot_summary(self) -> dict:
        """
        Return a concise summary dict for API responses and UI display.

        The Streamlit UI (Phase 5) will use this to show the current
        risk position alongside the agent's answer.
        """
        if not self._risk_snapshot:
            return {}
        ps = self._risk_snapshot.get("portfolio_summary", {})
        return {
            "snapshot_date": self._risk_snapshot.get("snapshot_date"),
            "total_vessels": ps.get("total_vessels"),
            "total_annual_fuel_cost_usd": ps.get("total_annual_fuel_cost_usd"),
            "portfolio_var_95_10d_usd": ps.get("portfolio_var_95_10d_usd"),
            "portfolio_var_99_10d_usd": ps.get("portfolio_var_99_10d_usd"),
            "portfolio_cvar_95_10d_usd": ps.get("portfolio_cvar_95_10d_usd"),
            "average_hedge_ratio_pct": ps.get("average_hedge_ratio_pct"),
        }
